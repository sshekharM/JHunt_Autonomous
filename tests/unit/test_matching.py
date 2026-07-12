"""
Unit tests for app.ml.matcher.compute_match().
No database or network I/O — pure function tests.
"""
import pytest
from app.ml.matcher import compute_match, meets_threshold


class TestComputeMatchReturnShape:
    def test_returns_required_keys(self):
        result = compute_match(["Python", "FastAPI"], ["Python", "Docker"])
        assert set(result.keys()) == {"score", "matched", "missing", "coverage_pct"}

    def test_score_is_float_in_range(self):
        result = compute_match(["Python"], ["Python", "Java"])
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 1.0

    def test_coverage_pct_is_float_in_range(self):
        result = compute_match(["Python", "Java"], ["Python", "Java", "Go"])
        assert isinstance(result["coverage_pct"], float)
        assert 0.0 <= result["coverage_pct"] <= 100.0


class TestComputeMatchEdgeCases:
    def test_empty_job_skills_returns_zero_score(self):
        result = compute_match(["Python", "FastAPI"], [])
        assert result["score"] == 0.0
        assert result["matched"] == []
        assert result["missing"] == []
        assert result["coverage_pct"] == 0.0

    def test_empty_user_skills_returns_zero_score(self):
        result = compute_match([], ["Python", "Docker"])
        assert result["score"] == 0.0
        assert result["matched"] == []
        assert result["missing"] == ["Python", "Docker"]
        assert result["coverage_pct"] == 0.0

    def test_both_empty_returns_zero(self):
        result = compute_match([], [])
        assert result["score"] == 0.0

    def test_single_skill_exact_match(self):
        result = compute_match(["Python"], ["Python"])
        assert result["score"] > 0.0
        assert "Python" in result["matched"]
        assert result["missing"] == []
        assert result["coverage_pct"] == 100.0

    def test_single_skill_no_match(self):
        result = compute_match(["Java"], ["Python"])
        assert result["matched"] == []
        assert "Python" in result["missing"]
        assert result["coverage_pct"] == 0.0


class TestComputeMatchExactMatching:
    def test_all_skills_matched(self):
        skills = ["Python", "FastAPI", "PostgreSQL", "Docker"]
        result = compute_match(skills, skills)
        assert result["coverage_pct"] == 100.0
        assert sorted(result["matched"]) == sorted(skills)
        assert result["missing"] == []

    def test_partial_match_correct_split(self):
        user_skills = ["Python", "FastAPI", "Redis"]
        job_skills = ["Python", "FastAPI", "Kubernetes", "Terraform"]
        result = compute_match(user_skills, job_skills)
        assert "Python" in result["matched"]
        assert "FastAPI" in result["matched"]
        assert "Kubernetes" in result["missing"]
        assert "Terraform" in result["missing"]
        assert result["coverage_pct"] == 50.0  # 2 of 4 matched

    def test_no_overlap_returns_all_missing(self):
        result = compute_match(["Ruby", "Rails"], ["Go", "Rust", "C++"])
        assert result["matched"] == []
        assert sorted(result["missing"]) == sorted(["Go", "Rust", "C++"])
        assert result["coverage_pct"] == 0.0


class TestComputeMatchCaseInsensitive:
    def test_case_insensitive_exact_match(self):
        result = compute_match(["python", "fastapi"], ["Python", "FastAPI"])
        assert "Python" in result["matched"]
        assert "FastAPI" in result["matched"]
        assert result["missing"] == []
        assert result["coverage_pct"] == 100.0

    def test_mixed_case_user_skills(self):
        result = compute_match(["KUBERNETES", "Docker"], ["kubernetes", "docker"])
        assert result["coverage_pct"] == 100.0


class TestComputeMatchScore:
    def test_higher_overlap_gives_higher_score(self):
        full_match = compute_match(["Python", "FastAPI", "PostgreSQL"], ["Python", "FastAPI", "PostgreSQL"])
        partial_match = compute_match(["Python"], ["Python", "FastAPI", "PostgreSQL"])
        assert full_match["score"] > partial_match["score"]

    def test_disjoint_skills_low_score(self):
        result = compute_match(
            ["Cobol", "Fortran", "Pascal"],
            ["Python", "Kubernetes", "Terraform", "Rust"],
        )
        # TF-IDF may give a small non-zero score for disjoint vocabularies
        assert result["score"] < 0.3

    def test_exact_full_overlap_high_score(self):
        skills = ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"]
        result = compute_match(skills, skills)
        assert result["score"] >= 0.9

    def test_score_is_deterministic(self):
        user = ["Python", "Django", "PostgreSQL"]
        job = ["Python", "Flask", "Redis"]
        r1 = compute_match(user, job)
        r2 = compute_match(user, job)
        assert r1["score"] == r2["score"]


class TestMeetsThreshold:
    def test_above_threshold(self):
        result = compute_match(["Python", "FastAPI", "PostgreSQL"], ["Python", "FastAPI", "PostgreSQL"])
        assert meets_threshold(result, 0.5) is True

    def test_below_threshold(self):
        result = compute_match([], ["Python", "Docker"])
        assert meets_threshold(result, 0.5) is False

    def test_exact_threshold_passes(self):
        fake_result = {"score": 0.75, "matched": [], "missing": [], "coverage_pct": 0.0}
        assert meets_threshold(fake_result, 0.75) is True

    def test_just_below_threshold_fails(self):
        fake_result = {"score": 0.7499, "matched": [], "missing": [], "coverage_pct": 0.0}
        assert meets_threshold(fake_result, 0.75) is False


class TestComputeMatchBlendedScore:
    def test_blended_score_not_purely_tfidf(self):
        # A job with one matching skill out of many: exact match ratio is low
        # but TF-IDF may return a higher value — blended score should differ from raw TF-IDF
        result = compute_match(
            ["Python"],
            ["Python", "Go", "Rust", "Kubernetes", "Terraform", "Ansible", "Jenkins"],
        )
        # 1/7 exact coverage → coverage_pct ~14.3
        assert result["coverage_pct"] == pytest.approx(14.3, abs=0.1)
        # Blended score should be lower than a hypothetical pure TF-IDF score of 1.0
        assert result["score"] < 1.0

    def test_large_matching_set_high_coverage(self):
        shared = [f"Skill{i}" for i in range(20)]
        extra_user = [f"Extra{i}" for i in range(10)]
        result = compute_match(shared + extra_user, shared)
        assert result["coverage_pct"] == 100.0
        assert result["missing"] == []
