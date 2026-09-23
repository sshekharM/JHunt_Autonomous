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
