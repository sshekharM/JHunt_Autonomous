"""
Characterization tests for app.services.screening_service.

Strategy: exact cached-answer lookup first, LLM fallback + caching for
unknowns. No real DB or LLM — everything is a fake/mock.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.screening_service import (
    _build_llm_prompt,
    _fingerprint,
    answer_screening_question,
    get_saved_answers,
)


# ---------------------------------------------------------------------------
# _fingerprint
# ---------------------------------------------------------------------------

def test_fingerprint_is_stable_and_16_chars():
    fp = _fingerprint("Do you have a valid work permit?")
    assert fp == _fingerprint("Do you have a valid work permit?")
    assert len(fp) == 16


def test_fingerprint_is_case_and_whitespace_insensitive():
    assert _fingerprint("  Are You Legally Authorized?  ") == _fingerprint(
        "are you legally authorized?"
    )


def test_fingerprint_differs_for_different_questions():
    assert _fingerprint("question a") != _fingerprint("question b")


# ---------------------------------------------------------------------------
# _build_llm_prompt
# ---------------------------------------------------------------------------

def test_build_llm_prompt_includes_portal_and_question():
    prompt = _build_llm_prompt(
        "Are you willing to relocate?",
        "linkedin",
        {"current_role": "Engineer", "years_exp": 5, "skills": ["Python", "SQL"], "city": "Pune", "state": "MH"},
    )
    assert "linkedin" in prompt
    assert "Are you willing to relocate?" in prompt
    assert "Engineer" in prompt
    assert "5" in prompt
    assert "Python, SQL" in prompt
    assert "Pune, MH" in prompt


def test_build_llm_prompt_defaults_missing_profile_fields():
    prompt = _build_llm_prompt("Q?", "indeed", {})
    assert "Not specified" in prompt
    assert "Years of experience: 0" in prompt


# ---------------------------------------------------------------------------
# answer_screening_question
# ---------------------------------------------------------------------------

def _db_returning(scalar_value):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_cache_hit_returns_saved_answer_without_llm_call():
    saved = MagicMock()
    saved.answer_text = "Yes, I have a valid work permit."
    db = _db_returning(saved)

    with patch("app.services.screening_service.llm_router.generate", new=AsyncMock()) as mock_gen:
        answer = await answer_screening_question(
            "Do you have a work permit?", "linkedin", {}, "gpt-4", db
        )

    assert answer == "Yes, I have a valid work permit."
    mock_gen.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


async def _run_cache_miss():
    db = _db_returning(None)
    with patch(
        "app.services.screening_service.llm_router.generate",
        new=AsyncMock(return_value="  Yes, I am authorized.  "),
    ) as mock_gen:
        answer = await answer_screening_question(
            "Are you authorized to work?", "indeed", {"current_role": "Dev"}, "claude", db
        )
    return db, mock_gen, answer


@pytest.mark.asyncio
async def test_cache_miss_calls_llm_with_prompt_and_choice():
    _, mock_gen, answer = await _run_cache_miss()
    assert answer == "Yes, I am authorized."
    mock_gen.assert_called_once()
    prompt_arg, choice_arg = mock_gen.call_args[0]
    assert "Are you authorized to work?" in prompt_arg
    assert choice_arg == "claude"


@pytest.mark.asyncio
async def test_cache_miss_caches_new_answer_with_expected_fields():
    db, _, _ = await _run_cache_miss()
    db.add.assert_called_once()
    entry = db.add.call_args[0][0]
    assert entry.portal == "indeed"
    assert entry.question_text == "Are you authorized to work?"
    assert entry.answer_text == "Yes, I am authorized."
    assert entry.auto_generated is True
    assert entry.user_verified is False
    assert entry.question_fingerprint == _fingerprint("Are you authorized to work?")
    db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_saved_answers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_saved_answers_keys_by_question_text():
    row1 = MagicMock(question_text="Q1", answer_text="A1")
    row2 = MagicMock(question_text="Q2", answer_text="A2")

    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row1, row2]
    db.execute = AsyncMock(return_value=result)

    answers = await get_saved_answers("linkedin", db)

    assert answers == {"Q1": "A1", "Q2": "A2"}
