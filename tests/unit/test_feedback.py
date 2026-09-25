"""
Characterization tests for app.ml.feedback.

No real DB -- every AsyncSession is a fake/mock.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ml import feedback
from app.tenant_models.ml_feedback import OutcomeSignal


def _db_with_rows(rows):
    db = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


async def _record_default_outcome(db):
    with patch("app.ml.feedback.audit") as mock_audit:
        await feedback.record_outcome(
            application_id="app-1",
            portal="linkedin",
            job_title="Backend Engineer",
            match_score=0.82,
            outcome=OutcomeSignal.interview_scheduled,
            tenant_db=db,
            user_id="user-1",
        )
    return mock_audit


@pytest.mark.asyncio
async def test_record_outcome_adds_feedback_row_with_given_fields():
    db = AsyncMock()
    db.add = MagicMock()

    await _record_default_outcome(db)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.application_id == "app-1"
    assert added.portal == "linkedin"
    assert added.job_title == "Backend Engineer"
    assert added.match_score_at_apply == 0.82
    assert added.outcome == OutcomeSignal.interview_scheduled


@pytest.mark.asyncio
async def test_record_outcome_commits_and_audits():
    db = AsyncMock()
    db.add = MagicMock()

    mock_audit = await _record_default_outcome(db)

    db.commit.assert_awaited_once()
    mock_audit.assert_called_once_with(
        "ml.feedback_recorded",
        user_id="user-1",
        details={"outcome": OutcomeSignal.interview_scheduled, "portal": "linkedin"},
    )


@pytest.mark.asyncio
async def test_compute_user_score_adjustment_skips_zero_total_portals():
    db = _db_with_rows([("linkedin", 0, 0)])

    adjustments = await feedback.compute_user_score_adjustment(db)

    assert adjustments == {}


@pytest.mark.asyncio
async def test_compute_user_score_adjustment_computes_boost_for_success_rate():
    # success_rate = 5/10 = 0.5 -> min(0.05, 0.5 * 0.1) = 0.05
    db = _db_with_rows([("linkedin", 5, 10)])

    adjustments = await feedback.compute_user_score_adjustment(db)

    assert adjustments == {"linkedin": 0.05}


@pytest.mark.asyncio
async def test_compute_user_score_adjustment_caps_at_point_zero_five():
    # success_rate = 10/10 = 1.0 -> raw = 0.1, capped at 0.05
    db = _db_with_rows([("indeed", 10, 10)])

    adjustments = await feedback.compute_user_score_adjustment(db)

    assert adjustments == {"indeed": 0.05}


@pytest.mark.asyncio
async def test_compute_user_score_adjustment_low_success_rate_below_cap():
    # success_rate = 1/10 = 0.1 -> 0.1 * 0.1 = 0.01, below cap
    db = _db_with_rows([("dice", 1, 10)])

    adjustments = await feedback.compute_user_score_adjustment(db)

    assert adjustments == {"dice": 0.01}
