"""
The match task scopes sessions with SET search_path; the schema name must be
validated before it is interpolated into that statement.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.security.encryption import generate_thumbprint, schema_name_from_thumbprint

VALID = schema_name_from_thumbprint(generate_thumbprint("a@b.com", "+919999999999"))


def _session_factory():
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.fetchall.return_value = []  # no skills -> early return
    session.execute = AsyncMock(return_value=result)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


@pytest.mark.asyncio
async def test_match_rejects_invalid_schema_before_sql():
    from app.tasks.match_jobs import _run_match_for_user
    factory, session = _session_factory()
    with patch("app.database.AsyncSessionLocal", factory), pytest.raises(ValueError):
        await _run_match_for_user("user-1", 'public"; DROP TABLE users; --')
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_match_opens_tenant_session_for_validated_schema():
    from app.tasks.match_jobs import _run_match_for_user
    factory, _session = _session_factory()
    with patch("app.database.AsyncSessionLocal", factory):
        result = await _run_match_for_user("user-1", VALID)
    assert result["skipped"] == "no_skills"
    # every session in the task is a tenant session for this user's schema
    assert factory.call_args_list[0].kwargs == {"info": {"tenant_schema": VALID}}


# ---------------------------------------------------------------------------
# Full match flow (with skills + jobs)
# ---------------------------------------------------------------------------

def _skills_session(skill_names):
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.fetchall.return_value = [
        MagicMock(skill_name=n) for n in skill_names
    ]
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


def _job(**overrides):
    job = {
        "portal": "linkedin",
        "portal_job_id": "j-1",
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Remote",
        "job_url": "https://example.com/j-1",
        "description": "x" * 600,
        "skills_required": ["Python"],
    }
    job.update(overrides)
    return job


async def _run_full_match(jobs, compute_match_result=None, score_adjustments=None):
    """Run the match flow. Kept free of any patch on app.tasks.notify: that
    module has no send_match_notification (see test_high_match_dispatch_
    currently_raises_importerror below) so tests here only exercise
    score/persistence branches that stay below HIGH_MATCH_THRESHOLD."""
    from app.tasks.match_jobs import _run_match_for_user

    factory, session = _skills_session(["Python"])
    with patch("app.database.AsyncSessionLocal", factory), patch(
        "app.services.job_service.get_unmatched_jobs", new=AsyncMock(return_value=jobs)
    ), patch(
        "app.ml.feedback.compute_user_score_adjustment",
        new=AsyncMock(return_value=score_adjustments or {}),
    ), patch(
        "app.ml.matcher.compute_match",
        return_value=compute_match_result or {"score": 0.5, "matched": ["Python"], "missing": [], "coverage_pct": 100.0},
    ) as mock_compute:
        result = await _run_match_for_user("user-1", VALID)
    return result, session, mock_compute


@pytest.mark.asyncio
async def test_match_returns_no_new_jobs_when_none_unmatched():
    result, session, _ = await _run_full_match([])
    assert result["skipped"] == "no_new_jobs"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_match_persists_job_with_snippet_and_score():
    jobs = [_job()]
    result, session, mock_compute = await _run_full_match(jobs)

    mock_compute.assert_called_once_with(["Python"], ["Python"])
    session.add.assert_called_once()
    matched_job = session.add.call_args[0][0]
    assert matched_job.match_score == 0.5
    assert len(matched_job.description_snippet) == 500
    assert result["matched"] == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_match_skips_compute_for_job_with_no_skills_required():
    jobs = [_job(skills_required=[], description="")]
    result, session, mock_compute = await _run_full_match(jobs)

    mock_compute.assert_not_called()
    matched_job = session.add.call_args[0][0]
    assert matched_job.match_score == 0.0
    assert matched_job.description_snippet is None
    assert result["matched"] == 1


@pytest.mark.asyncio
async def test_match_applies_portal_score_adjustment():
    jobs = [_job()]
    result, session, _ = await _run_full_match(
        jobs,
        compute_match_result={"score": 0.3, "matched": [], "missing": [], "coverage_pct": 0.0},
        score_adjustments={"linkedin": 0.2},
    )

    matched_job = session.add.call_args[0][0]
    assert matched_job.match_score == 0.5
    assert matched_job.explainability["portal_adjustment"] == 0.2
    assert result["high_match"] == 0


@pytest.mark.asyncio
async def test_match_does_not_dispatch_below_threshold_without_touching_notify():
    """Below HIGH_MATCH_THRESHOLD, notify.send_match_notification is never
    imported/called, so this passes even though that name does not exist."""
    jobs = [_job()]
    result, _, _ = await _run_full_match(
        jobs,
        compute_match_result={"score": 0.5, "matched": [], "missing": [], "coverage_pct": 0.0},
    )
    assert result["high_match"] == 0


@pytest.mark.asyncio
async def test_high_match_job_queues_a_match_notification():
    """Given a job that clears HIGH_MATCH_THRESHOLD, when matching runs, then a
    match notification is queued for that user's schema. (This used to raise
    ImportError: notify.send_match_notification did not exist.)"""
    from app.tasks.match_jobs import _run_match_for_user

    jobs = [_job()]
    factory, _ = _skills_session(["Python"])
    with patch("app.database.AsyncSessionLocal", factory), patch(
        "app.services.job_service.get_unmatched_jobs", new=AsyncMock(return_value=jobs)
    ), patch(
        "app.ml.feedback.compute_user_score_adjustment", new=AsyncMock(return_value={})
    ), patch(
        "app.ml.matcher.compute_match",
        return_value={"score": 0.9, "matched": ["Python"], "missing": [], "coverage_pct": 100.0},
    ), patch("app.tasks.notify.send_match_notification") as mock_task:
        result = await _run_match_for_user("user-1", VALID)

    assert result["high_match"] == 1
    mock_task.delay.assert_called_once_with("user-1", VALID, [{
        "portal": "linkedin", "portal_job_id": "j-1",
        "title": "Backend Engineer", "company": "Acme", "score": 0.9,
    }])


# ---------------------------------------------------------------------------
# _run_match_all_users
# ---------------------------------------------------------------------------

def _users_session(users):
    session = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = users
    session.execute = AsyncMock(return_value=result)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.mark.asyncio
async def test_run_match_all_users_aggregates_results():
    from app.tasks.match_jobs import _run_match_all_users

    factory = _users_session([("u1", "s1"), ("u2", "s2")])
    with patch("app.database.AsyncSessionLocal", factory), patch(
        "app.tasks.match_jobs._run_match_for_user",
        new=AsyncMock(side_effect=[{"matched": 3}, {"matched": 2}]),
    ), patch("app.tasks.match_jobs.audit") as mock_audit:
        summary = await _run_match_all_users()

    assert summary == {"total_users": 2, "total_matched": 5, "failed_users": 0}
    mock_audit.assert_called_once_with("match.completed", details=summary)


@pytest.mark.asyncio
async def test_run_match_all_users_counts_failures_without_raising():
    from app.tasks.match_jobs import _run_match_all_users

    factory = _users_session([("u1", "s1"), ("u2", "s2")])
    with patch("app.database.AsyncSessionLocal", factory), patch(
        "app.tasks.match_jobs._run_match_for_user",
        new=AsyncMock(side_effect=[RuntimeError("boom"), {"matched": 4}]),
    ), patch("app.tasks.match_jobs.audit") as mock_audit:
        summary = await _run_match_all_users()

    assert summary == {"total_users": 2, "total_matched": 4, "failed_users": 1}
    mock_audit.assert_any_call("match.completed", details=summary)
    assert mock_audit.call_count == 2
    failure_call = mock_audit.call_args_list[0]
    assert failure_call.args == ("match.user_failed",)
    assert failure_call.kwargs["user_id"] == "u1"
    assert isinstance(failure_call.kwargs["error"], RuntimeError)


# ---------------------------------------------------------------------------
# Celery task wrappers
# ---------------------------------------------------------------------------

def test_match_all_users_task_returns_summary_on_success():
    from app.tasks.match_jobs import match_all_users

    with patch(
        "app.tasks.match_jobs._run_match_all_users",
        new=AsyncMock(return_value={"total_users": 1, "total_matched": 1, "failed_users": 0}),
    ):
        result = match_all_users.run()

    assert result == {"total_users": 1, "total_matched": 1, "failed_users": 0}


def test_match_all_users_task_reraises_on_failure():
    from app.tasks.match_jobs import match_all_users

    with patch(
        "app.tasks.match_jobs._run_match_all_users",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ), pytest.raises(RuntimeError):
        match_all_users.run()


def test_match_jobs_for_user_task_returns_result_on_success():
    from app.tasks.match_jobs import match_jobs_for_user

    with patch(
        "app.tasks.match_jobs._run_match_for_user",
        new=AsyncMock(return_value={"user_id": "u1", "matched": 2, "high_match": 0}),
    ):
        result = match_jobs_for_user.run("u1", VALID)

    assert result == {"user_id": "u1", "matched": 2, "high_match": 0}


def test_match_jobs_for_user_task_reraises_on_failure():
    from app.tasks.match_jobs import match_jobs_for_user

    with patch(
        "app.tasks.match_jobs._run_match_for_user",
        new=AsyncMock(side_effect=RuntimeError("bad schema")),
    ), pytest.raises(RuntimeError):
        match_jobs_for_user.run("u1", VALID)


async def _run_scored(score):
    """Run one job through matching at a fixed score; return (result, session, task mock)."""
    from app.tasks.match_jobs import _run_match_for_user

    factory, session = _skills_session(["Python"])
    with patch("app.database.AsyncSessionLocal", factory), patch(
        "app.services.job_service.get_unmatched_jobs", new=AsyncMock(return_value=[_job()])
    ), patch(
        "app.ml.feedback.compute_user_score_adjustment", new=AsyncMock(return_value={})
    ), patch(
        "app.ml.matcher.compute_match",
        return_value={"score": score, "matched": ["Python"], "missing": [], "coverage_pct": 100.0},
    ), patch("app.tasks.notify.send_match_notification") as mock_task:
        result = await _run_match_for_user("user-1", VALID)
    return result, session, mock_task


@pytest.mark.asyncio
async def test_a_score_exactly_at_the_threshold_counts_as_a_high_match():
    from app.tasks.match_jobs import HIGH_MATCH_THRESHOLD

    result, _, mock_task = await _run_scored(HIGH_MATCH_THRESHOLD)
    assert result["high_match"] == 1
    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_matched_jobs_are_stored_as_active():
    from app.tenant_models.job import MatchedJob

    _, session, _ = await _run_scored(0.9)
    [stored] = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], MatchedJob)]
    assert stored.is_active is True


@pytest.mark.asyncio
async def test_run_match_all_users_selects_only_active_onboarded_users():
    from sqlalchemy.dialects import postgresql

    from app.tasks.match_jobs import _run_match_all_users

    factory = _users_session([])
    with patch("app.database.AsyncSessionLocal", factory):
        await _run_match_all_users()

    session = factory.return_value.__aenter__.return_value
    stmt = session.execute.await_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "users.is_active IS true" in sql
    assert "users.onboarding_complete IS true" in sql
