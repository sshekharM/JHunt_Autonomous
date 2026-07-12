"""
Unit tests for applications router endpoint logic.
Calls endpoint functions directly with mocked dependencies.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenant_models.application import ApplicationStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(schema="u_test"):
    u = MagicMock()
    u.id = "user-001"
    u.schema_name = schema
    return u


def _make_prefs(**kwargs):
    defaults = dict(
        company_blacklist=[],
        title_blacklist=[],
        auto_apply_paused=False,
        pause_until=None,
    )
    defaults.update(kwargs)
    p = MagicMock()
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


def _mock_tenant_db(prefs):
    """Return an async-generator that yields a mock AsyncSession returning prefs."""
    db = AsyncMock(spec=AsyncSession)
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = prefs
    db.execute = AsyncMock(return_value=scalar_result)
    db.commit = AsyncMock()

    async def _gen(schema_name):
        yield db

    return _gen, db


# ---------------------------------------------------------------------------
# Pause
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pause_sets_paused_flag():
    from app.routers.applications import pause_auto_apply, PauseRequest

    prefs = _make_prefs()
    gen, db = _mock_tenant_db(prefs)
    user = _make_user()

    with patch("app.routers.applications.get_tenant_db", gen):
        result = await pause_auto_apply(body=PauseRequest(minutes=120), user=user)

    assert result["ok"] is True
    assert prefs.auto_apply_paused is True
    assert prefs.pause_until is not None
    # pause_until should be in the future
    assert prefs.pause_until > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_delete_pause_clears_flags():
    from app.routers.applications import resume_auto_apply

    prefs = _make_prefs(
        auto_apply_paused=True,
        pause_until=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    gen, db = _mock_tenant_db(prefs)
    user = _make_user()

    with patch("app.routers.applications.get_tenant_db", gen):
        result = await resume_auto_apply(user=user)

    assert result["ok"] is True
    assert prefs.auto_apply_paused is False
    assert prefs.pause_until is None


# ---------------------------------------------------------------------------
# Company blacklist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_company_blacklist():
    from app.routers.applications import add_company_blacklist, CompanyBlacklistRequest

    prefs = _make_prefs(company_blacklist=[])
    gen, db = _mock_tenant_db(prefs)
    user = _make_user()

    with patch("app.routers.applications.get_tenant_db", gen):
        result = await add_company_blacklist(
            body=CompanyBlacklistRequest(name="Evil Corp"), user=user
        )

    assert result["ok"] is True
    assert "Evil Corp" in prefs.company_blacklist


@pytest.mark.asyncio
async def test_remove_company_blacklist():
    from app.routers.applications import remove_company_blacklist

    prefs = _make_prefs(company_blacklist=["Evil Corp", "Bad Inc"])
    gen, db = _mock_tenant_db(prefs)
    user = _make_user()

    with patch("app.routers.applications.get_tenant_db", gen):
        result = await remove_company_blacklist(name="Evil Corp", user=user)

    assert result["ok"] is True
    assert "Evil Corp" not in prefs.company_blacklist
    assert "Bad Inc" in prefs.company_blacklist


# ---------------------------------------------------------------------------
# Title blacklist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_title_blacklist():
    from app.routers.applications import add_title_blacklist, TitleBlacklistRequest

    prefs = _make_prefs(title_blacklist=[])
    gen, db = _mock_tenant_db(prefs)
    user = _make_user()

    with patch("app.routers.applications.get_tenant_db", gen):
        result = await add_title_blacklist(
            body=TitleBlacklistRequest(title="PHP Developer"), user=user
        )

    assert result["ok"] is True
    assert "PHP Developer" in prefs.title_blacklist


@pytest.mark.asyncio
async def test_remove_title_blacklist():
    from app.routers.applications import remove_title_blacklist

    prefs = _make_prefs(title_blacklist=["PHP Developer", "COBOL Dev"])
    gen, db = _mock_tenant_db(prefs)
    user = _make_user()

    with patch("app.routers.applications.get_tenant_db", gen):
        result = await remove_title_blacklist(title="PHP Developer", user=user)

    assert result["ok"] is True
    assert "PHP Developer" not in prefs.title_blacklist
    assert "COBOL Dev" in prefs.title_blacklist


# ---------------------------------------------------------------------------
# Withdraw
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_withdraw_calls_transition_status():
    from app.routers.applications import withdraw_application

    user = _make_user()

    mock_db = AsyncMock(spec=AsyncSession)

    async def _gen(schema_name):
        yield mock_db

    mock_transition = AsyncMock()

    with patch("app.routers.applications.get_tenant_db", _gen), \
         patch("app.routers.applications.transition_status", mock_transition):
        await withdraw_application(application_id="app-abc", user=user)

    mock_transition.assert_called_once()
    call_kwargs = mock_transition.call_args[1]
    assert call_kwargs["application_id"] == "app-abc"
    assert call_kwargs["new_status"] == ApplicationStatus.withdrawn
