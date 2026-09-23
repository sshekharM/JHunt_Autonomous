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
    factory, session = _session_factory()
    with patch("app.database.AsyncSessionLocal", factory):
        result = await _run_match_for_user("user-1", VALID)
    assert result["skipped"] == "no_skills"
    # every session in the task is a tenant session for this user's schema
    assert factory.call_args_list[0].kwargs == {"info": {"tenant_schema": VALID}}
