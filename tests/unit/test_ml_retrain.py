"""
Nightly retrain scopes sessions with SET search_path; the schema name must be
validated before it is interpolated into that statement.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.security.encryption import generate_thumbprint, schema_name_from_thumbprint

VALID = schema_name_from_thumbprint(generate_thumbprint("a@b.com", "+919999999999"))


def _session_factory():
    session = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = []  # no feedback -> early return
    session.execute = AsyncMock(return_value=result)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


@pytest.mark.asyncio
async def test_retrain_rejects_invalid_schema_before_sql():
    from app.tasks.ml_retrain import _retrain_for_user
    factory, session = _session_factory()
    with patch("app.database.AsyncSessionLocal", factory), pytest.raises(ValueError):
        await _retrain_for_user("user-1", "public")
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_retrain_opens_tenant_session_for_validated_schema():
    from app.tasks.ml_retrain import _retrain_for_user
    factory, session = _session_factory()
    with patch("app.database.AsyncSessionLocal", factory):
        result = await _retrain_for_user("user-1", VALID)
    assert result["status"] == "no_feedback"
    # every session in the task is a tenant session for this user's schema
    assert factory.call_args_list[0].kwargs == {"info": {"tenant_schema": VALID}}


@pytest.mark.asyncio
async def test_retrain_logs_cache_invalidation_failure():
    """A failed skill_match_cache purge is logged, not swallowed; retrain still completes."""
    from app.tasks import ml_retrain
    factory, session = _session_factory()
    ok = MagicMock()
    ok.fetchall.return_value = [("naukri", "interview_scheduled", 0.8, 1)]

    async def execute(stmt, *args, **kwargs):
        if "skill_match_cache" in str(stmt):
            raise RuntimeError("table missing")
        return ok

    session.execute = AsyncMock(side_effect=execute)
    session.commit = AsyncMock()
    with patch("app.database.AsyncSessionLocal", factory), \
            patch.object(ml_retrain, "audit"), patch.object(ml_retrain, "logger") as log:
        result = await ml_retrain._retrain_for_user("user-1", VALID)

    assert result["status"] == "ok"
    log.warning.assert_called_once()
    assert log.warning.call_args.args[0] == "ml_retrain.cache_invalidation_failed"
    assert log.warning.call_args.kwargs.get("user_id") == "user-1"
    assert log.warning.call_args.kwargs.get("exc_info") is True


# --- stale tailored-resume purge -------------------------------------------

@pytest.mark.asyncio
async def test_purge_is_a_no_op_when_retention_disabled():
    from app.tasks import ml_retrain
    schemas = AsyncMock()
    with patch.object(ml_retrain.settings, "resume_retention_days", 0), \
            patch.object(ml_retrain, "_tenant_schemas", schemas):
        assert await ml_retrain._purge_stale_resumes_async() == {"tenants": 0, "purged": 0, "errors": 0}
    schemas.assert_not_called()


@pytest.mark.asyncio
async def test_purge_continues_past_a_failing_tenant():
    from app.tasks import ml_retrain
    per_tenant = AsyncMock(side_effect=[RuntimeError("schema gone"), (3, 1)])
    with patch.object(ml_retrain.settings, "resume_retention_days", 7), \
            patch.object(ml_retrain, "_tenant_schemas", AsyncMock(return_value=[VALID, VALID])), \
            patch.object(ml_retrain, "_purge_tenant_resumes", per_tenant), \
            patch.object(ml_retrain, "logger") as log:
        summary = await ml_retrain._purge_stale_resumes_async()
    assert summary == {"tenants": 2, "purged": 3, "errors": 2}
    assert log.error.call_args.args[0] == "purge_stale_resumes.tenant_failed"


def _resume(key):
    return MagicMock(minio_key=key, purged=False)


@pytest.mark.asyncio
async def test_failed_object_delete_leaves_row_unpurged():
    from datetime import datetime, timezone
    from app.tasks import ml_retrain
    ok, bad = _resume("u/ok.pdf"), _resume("u/bad.pdf")
    session = MagicMock(commit=AsyncMock())
    session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=[ok, bad])))
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    delete = AsyncMock(side_effect=[None, RuntimeError("access denied")])
    with patch("app.database.AsyncSessionLocal", factory), \
            patch("app.services.storage_service.delete_object", delete):
        result = await ml_retrain._purge_tenant_resumes(VALID, datetime.now(timezone.utc))
    assert result == (1, 1)
    assert ok.purged is True and bad.purged is False
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_tenant_schemas_selects_provisioned_users_only():
    from app.tasks import ml_retrain
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=[VALID])))
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("app.database.AsyncSessionLocal", factory):
        assert await ml_retrain._tenant_schemas() == [VALID]
    sql = str(session.execute.call_args.args[0])
    assert "users.schema_name != :schema_name_1" in sql


# --- per-portal adjustment rules ---------------------------------------------

async def _adjustments(rows):
    """Run _retrain_for_user over feedback rows (portal, outcome, avg_score, count)."""
    from app.tasks import ml_retrain
    factory, session = _session_factory()
    session.execute.return_value.fetchall.return_value = rows
    session.commit = AsyncMock()
    with patch("app.database.AsyncSessionLocal", factory), patch.object(ml_retrain, "audit"):
        result = await ml_retrain._retrain_for_user("user-1", VALID)
    return result["adjustments"]


@pytest.mark.asyncio
async def test_portal_with_exactly_min_samples_is_adjusted():
    from app.tasks.ml_retrain import MIN_FEEDBACK_SAMPLES
    rows = [("naukri", "offer_received", 0.8, 3), ("naukri", "no_response", 0.5, MIN_FEEDBACK_SAMPLES - 3)]
    assert "naukri" in await _adjustments(rows)


@pytest.mark.asyncio
async def test_portal_below_min_samples_is_skipped():
    from app.tasks.ml_retrain import MIN_FEEDBACK_SAMPLES
    assert await _adjustments([("naukri", "offer_received", 0.8, MIN_FEEDBACK_SAMPLES - 1)]) == {}


@pytest.mark.asyncio
async def test_half_success_rate_gets_the_boost_formula():
    rows = [("naukri", "offer_received", 0.8, 5), ("naukri", "no_response", 0.5, 5)]
    assert (await _adjustments(rows))["naukri"] == 0.06  # min(0.08, 0.5 * 0.12)


@pytest.mark.asyncio
async def test_low_success_rate_gets_the_penalty_formula():
    rows = [("naukri", "offer_received", 0.8, 1), ("naukri", "no_response", 0.5, 9)]
    assert (await _adjustments(rows))["naukri"] == -0.02  # (0.1 - 0.3) * 0.1


@pytest.mark.asyncio
async def test_retrain_all_selects_active_onboarded_users():
    from app.tasks import ml_retrain
    factory, session = _session_factory()
    session.execute.return_value.fetchall.return_value = []
    with patch("app.database.AsyncSessionLocal", factory), patch.object(ml_retrain, "audit"):
        assert (await ml_retrain._retrain_all())["total_users"] == 0
    sql = str(session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "users.is_active IS true" in sql and "users.onboarding_complete IS true" in sql
