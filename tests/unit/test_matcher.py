"""
Characterization tests for app.ml.matcher.

No real ML calls: sentence-transformers is not installed in this
environment, so the semantic path exercises its real ImportError
fallback. TF-IDF failures are exercised with a monkeypatched vectorizer.
Semantic scoring itself is exercised via a fake model (no downloads).
"""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.ml import matcher


_FAKE_EMBED_DIM = 4
_FAKE_SKILL_AXIS = {"python": 0, "go": 1, "java": 2, "kubernetes": 3}


class _FakeModel:
    """Fake sentence-transformers model with a fixed embedding dimension:
    each known skill gets a unit vector on its own axis, so identical
    skill names are perfectly similar and distinct ones are orthogonal."""

    def encode(self, skills, convert_to_numpy=True):
        embeddings = np.zeros((len(skills), _FAKE_EMBED_DIM))
        for idx, skill in enumerate(skills):
            axis = _FAKE_SKILL_AXIS[skill.lower()]
            embeddings[idx, axis] = 1.0
        return embeddings


def test_compute_match_returns_zero_when_job_skills_empty():
    result = matcher.compute_match(["Python"], [])

    assert result == {"score": 0.0, "matched": [], "missing": [], "coverage_pct": 0.0}


def test_compute_match_returns_zero_when_user_skills_empty():
    result = matcher.compute_match([], ["Python", "SQL"])

    assert result["score"] == 0.0
    assert result["matched"] == []
    assert result["missing"] == ["Python", "SQL"]
    assert result["coverage_pct"] == 0.0


def test_compute_match_exact_overlap_scores_high():
    result = matcher.compute_match(["Python", "FastAPI"], ["Python", "FastAPI"])

    assert result["matched"] == ["Python", "FastAPI"]
    assert result["missing"] == []
    assert result["coverage_pct"] == 100.0
    assert result["score"] > 0.9


def test_compute_match_partial_overlap_reports_missing():
    result = matcher.compute_match(["Python"], ["Python", "Kubernetes"])

    assert result["matched"] == ["Python"]
    assert result["missing"] == ["Kubernetes"]
    assert result["coverage_pct"] == 50.0


def test_compute_match_is_case_insensitive_for_exact_matches():
    result = matcher.compute_match(["python"], ["Python"])

    assert result["matched"] == ["Python"]
    assert result["missing"] == []


def test_tfidf_match_falls_back_to_zero_score_on_vectorizer_error():
    with patch(
        "app.ml.matcher.TfidfVectorizer",
        side_effect=ValueError("boom"),
    ):
        result = matcher._tfidf_match(["Python"], ["Java"])

    # exact-match ratio still applies: no overlap -> blended score 0.0
    assert result["score"] == 0.0
    assert result["matched"] == []
    assert result["missing"] == ["Java"]


def test_get_st_model_returns_none_when_sentence_transformers_missing():
    # sentence-transformers is not installed in this test environment,
    # so the real ImportError path runs.
    matcher._st_model = None

    with patch("app.ml.matcher.logger") as mock_logger:
        model = matcher._get_st_model()

    assert model is None
    mock_logger.info.assert_called_once()


def test_compute_match_with_use_semantic_falls_back_to_tfidf_when_unavailable():
    matcher._st_model = None

    result = matcher.compute_match(["Python"], ["Python"], use_semantic=True)

    assert result["matched"] == ["Python"]


def test_compute_match_uses_tfidf_when_use_semantic_false_even_with_model_available():
    """Pins the `use_semantic and _get_st_model()` guard: a semantic model
    that would score differently must NOT be used when use_semantic=False."""
    with patch("app.ml.matcher._get_st_model", return_value=_FakeModel()):
        semantic_result = matcher._semantic_match(["Java"], ["Python"])
        tfidf_result = matcher.compute_match(["Java"], ["Python"], use_semantic=False)

    # semantic match of orthogonal skills would report no match at all;
    # tfidf still reports the (non-matching) skill via exact-match logic
    assert semantic_result["matched"] == []
    assert tfidf_result == matcher._tfidf_match(["Java"], ["Python"])


def test_compute_match_defaults_use_semantic_to_false():
    """Pins the default value of use_semantic: omitting it must behave
    identically to passing use_semantic=False, even when a semantic model
    is available and would produce a different result."""
    with patch("app.ml.matcher._get_st_model", return_value=_FakeModel()):
        default_result = matcher.compute_match(["Java"], ["Python"])

    assert default_result == matcher._tfidf_match(["Java"], ["Python"])


def test_semantic_match_falls_back_to_tfidf_when_model_unavailable():
    matcher._st_model = None

    result = matcher._semantic_match(["Python"], ["Python", "Go"])

    assert result["matched"] == ["Python"]
    assert result["missing"] == ["Go"]


def test_semantic_match_uses_model_similarity_when_available():
    fake_model = _FakeModel()
    fake_model.encode = MagicMock(wraps=fake_model.encode)

    with patch("app.ml.matcher._get_st_model", return_value=fake_model):
        result = matcher._semantic_match(["Python", "Java"], ["Python", "Kubernetes"])

    assert result["matched"] == ["Python"]
    assert result["missing"] == ["Kubernetes"]
    assert result["score"] == 0.5
    assert result["coverage_pct"] == 50.0
    # encoding must request numpy arrays (the rest of the function relies
    # on numpy operations such as np.linalg.norm)
    for call in fake_model.encode.call_args_list:
        assert call.kwargs["convert_to_numpy"] is True


def test_semantic_match_boundary_at_exact_threshold_counts_as_matched():
    """max_sim == SEMANTIC_THRESHOLD (0.75) must count as matched, pinning
    the `>=` comparison against an off-by-boundary `>` mutation."""
    boundary_model = MagicMock()
    user_vec = np.array([[1.0, 0.0]])
    # dx chosen so that, after this function's epsilon-adjusted
    # normalization (norm + 1e-8), the resulting cosine similarity is
    # exactly 0.75 in float64 -- not merely close to it.
    dx = 0.750000015
    job_vec = np.array([[dx, (1 - dx**2) ** 0.5]])
    boundary_model.encode.side_effect = [user_vec, job_vec]

    with patch("app.ml.matcher._get_st_model", return_value=boundary_model):
        result = matcher._semantic_match(["Python"], ["Python"])

    assert result["matched"] == ["Python"]
    assert result["missing"] == []


def test_semantic_match_falls_back_to_tfidf_on_encode_error():
    broken_model = MagicMock()
    broken_model.encode.side_effect = RuntimeError("model crashed")

    with patch("app.ml.matcher._get_st_model", return_value=broken_model):
        result = matcher._semantic_match(["Python"], ["Python"])

    assert result["matched"] == ["Python"]


@pytest.mark.parametrize(
    "score,threshold,expected",
    [
        (0.75, 0.7, True),
        (0.7, 0.7, True),
        (0.5, 0.7, False),
    ],
)
def test_meets_threshold(score, threshold, expected):
    assert matcher.meets_threshold({"score": score}, threshold) is expected
