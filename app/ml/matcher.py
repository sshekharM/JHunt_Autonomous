"""
TF-IDF cosine similarity skill matcher.

Input:  user skill list + job required skill list
Output: match score (0.0–1.0) + explainability dict
        {"matched": ["Python", "FastAPI"], "missing": ["Kubernetes"], "score": 0.73}

Phase 2 (sentence-transformers semantic similarity) is scaffolded below.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from typing import Optional
import structlog

logger = structlog.get_logger("ml.matcher")

# Sentence-transformers scaffold — import guarded, activated in Phase 5
_st_model = None


def _get_st_model():
    global _st_model
    if _st_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            pass
    return _st_model


def compute_match(
    user_skills: list[str],
    job_skills: list[str],
    use_semantic: bool = False,
) -> dict:
    """
    Compute skill match between user and job.

    Returns:
        {
            "score": 0.73,
            "matched": ["Python", "FastAPI", "PostgreSQL"],
            "missing": ["Kubernetes", "Terraform"],
            "coverage_pct": 73.0,
        }
    """
    if not job_skills:
        return {"score": 0.0, "matched": [], "missing": [], "coverage_pct": 0.0}
    if not user_skills:
        return {"score": 0.0, "matched": [], "missing": job_skills, "coverage_pct": 0.0}

    if use_semantic and _get_st_model():
        return _semantic_match(user_skills, job_skills)

    return _tfidf_match(user_skills, job_skills)


def _tfidf_match(user_skills: list[str], job_skills: list[str]) -> dict:
    """TF-IDF cosine similarity match."""
    user_text = " ".join(s.lower() for s in user_skills)
    job_text = " ".join(s.lower() for s in job_skills)

    try:
        vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2))
        matrix = vectorizer.fit_transform([user_text, job_text])
        score = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    except Exception as exc:
        logger.warning("matcher.tfidf_error", error=str(exc))
        score = 0.0

    # Exact / near-exact skill matching for explainability
    user_lower = {s.lower() for s in user_skills}
    matched = [s for s in job_skills if s.lower() in user_lower]
    missing = [s for s in job_skills if s.lower() not in user_lower]

    # Boost score based on exact matches
    if job_skills:
        exact_ratio = len(matched) / len(job_skills)
        # Weighted average: 60% TF-IDF similarity + 40% exact match ratio
        blended_score = round(0.6 * score + 0.4 * exact_ratio, 4)
    else:
        blended_score = score

    coverage_pct = round(len(matched) / len(job_skills) * 100, 1) if job_skills else 0.0

    return {
        "score": blended_score,
        "matched": matched,
        "missing": missing,
        "coverage_pct": coverage_pct,
    }


def _semantic_match(user_skills: list[str], job_skills: list[str]) -> dict:
    """
    Sentence-transformers semantic similarity — Phase 5.
    Encodes each skill individually and computes pairwise cosine similarities.
    A job skill is matched if any user skill embedding is >= 0.75 cosine similar.
    Falls back to TF-IDF if model unavailable.
    """
    model = _get_st_model()
    if not model:
        return _tfidf_match(user_skills, job_skills)

    SEMANTIC_THRESHOLD = 0.75

    try:
        user_embs = model.encode(user_skills, convert_to_numpy=True)
        job_embs = model.encode(job_skills, convert_to_numpy=True)

        # Normalise for cosine similarity via dot product
        user_norms = np.linalg.norm(user_embs, axis=1, keepdims=True) + 1e-8
        job_norms = np.linalg.norm(job_embs, axis=1, keepdims=True) + 1e-8
        user_embs_n = user_embs / user_norms
        job_embs_n = job_embs / job_norms

        # similarity matrix: shape (num_job_skills, num_user_skills)
        sim_matrix = job_embs_n @ user_embs_n.T

        matched = []
        missing = []
        for idx, job_skill in enumerate(job_skills):
            max_sim = float(sim_matrix[idx].max())
            if max_sim >= SEMANTIC_THRESHOLD:
                matched.append(job_skill)
            else:
                missing.append(job_skill)

        score = round(len(matched) / len(job_skills), 4) if job_skills else 0.0
        coverage_pct = round(len(matched) / len(job_skills) * 100, 1) if job_skills else 0.0
        return {"score": score, "matched": matched, "missing": missing, "coverage_pct": coverage_pct}

    except Exception as exc:
        logger.error("matcher.semantic_error", error=str(exc))
        return _tfidf_match(user_skills, job_skills)


def meets_threshold(match_result: dict, threshold: float) -> bool:
    return match_result["score"] >= threshold
