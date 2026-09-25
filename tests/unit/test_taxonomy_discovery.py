"""
Characterization tests for app.ml.taxonomy_discovery.

No real DB or LLM calls -- AsyncSession and the category-suggestion
callback are fakes.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ml import taxonomy_discovery
from app.ml.taxonomy_discovery import SoftSignals, activate_soft_signals


def _db_no_existing():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _db_with_existing():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = object()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# extract_candidate_skills
# ---------------------------------------------------------------------------

def test_extract_candidate_skills_finds_new_tech_terms():
    jd = "We need someone skilled in Python and Kubernetes for this Job."
    candidates = taxonomy_discovery.extract_candidate_skills(jd, known_skills=set())

    assert "Python" in candidates
    assert "Kubernetes" in candidates


def test_extract_candidate_skills_excludes_stopwords():
    jd = "The Team must have Strong Experience."
    candidates = taxonomy_discovery.extract_candidate_skills(jd, known_skills=set())

    assert candidates == []


def test_extract_candidate_skills_excludes_known_skills_case_insensitive():
    jd = "Must know Python well."
    candidates = taxonomy_discovery.extract_candidate_skills(jd, known_skills={"python"})

    assert "Python" not in candidates


def test_extract_candidate_skills_caps_at_twenty():
    jd = " ".join(f"Skill{i}" for i in range(30))
    candidates = taxonomy_discovery.extract_candidate_skills(jd, known_skills=set())

    assert len(candidates) == 20


# ---------------------------------------------------------------------------
# queue_discovered_skills
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queue_discovered_skills_skips_existing_skill():
    db = _db_with_existing()

    queued = await taxonomy_discovery.queue_discovered_skills(["Python"], db)

    assert queued == 0
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_discovered_skills_adds_new_skill_and_commits():
    db = _db_no_existing()

    queued = await taxonomy_discovery.queue_discovered_skills(["Rust"], db)

    assert queued == 1
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.skill_name == "Rust"
    assert added.category == "uncategorised"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_queue_discovered_skills_uses_llm_suggestion_when_provided():
    db = _db_no_existing()
    suggest = AsyncMock(return_value="Languages")

    await taxonomy_discovery.queue_discovered_skills(["Rust"], db, llm_suggest_category_fn=suggest)

    suggest.assert_awaited_once_with("Rust")
    added = db.add.call_args[0][0]
    assert added.auto_suggested_category == "Languages"


# ---------------------------------------------------------------------------
# SoftSignals / activate_soft_signals
# ---------------------------------------------------------------------------

def test_soft_signals_score_is_zero_when_disabled():
    SoftSignals.enabled = False

    score = SoftSignals.score(
        {"company_size": "large", "is_remote": True},
        {"preferred_company_size": "large", "wfh_preference": "remote"},
    )

    assert score == 0.0


def test_soft_signals_score_rewards_matching_preferences_when_enabled():
    SoftSignals.enabled = True
    try:
        score = SoftSignals.score(
            {"company_size": "large", "is_remote": True},
            {"preferred_company_size": "large", "wfh_preference": "remote"},
        )
    finally:
        SoftSignals.enabled = False

    assert score == 0.05


def test_activate_soft_signals_enables_flag():
    SoftSignals.enabled = False
    try:
        activate_soft_signals()
        assert SoftSignals.enabled is True
    finally:
        SoftSignals.enabled = False
