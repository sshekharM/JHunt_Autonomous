"""
Fills the coverage gaps in app/routers/applications.py left by
test_applications_router.py: listing/filtering, single-application detail,
the 404 branches for pause/resume/blacklist, the "no-op when duplicate" branch
of the blacklist add handlers, the empty-prefs branch of get_blacklists, and
account deletion mode validation.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.routers import applications
from app.tenant_models.application import ApplicationFailureReason, ApplicationStatus


def _user(schema="u_test"):
    return SimpleNamespace(id="user-001", schema_name=schema)


def _prefs(**kwargs):
    defaults = dict(company_blacklist=[], title_blacklist=[], auto_apply_paused=False, pause_until=None)
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class _RecordingTenantDB:
    """Captures every select this router issues and answers with queued results."""

    def __init__(self, results=None):
        self._results = list(results or [])
        self.executed = []
        self.commits = 0

    async def execute(self, stmt):
        self.executed.append(stmt)
        if self._results:
            return self._results.pop(0)
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    async def commit(self):
        self.commits += 1


def _tenant_gen(db):
    async def gen(schema_name):
        yield db
    return gen


def _sql(stmt):
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _app_row(**kwargs):
    defaults = dict(
        id="app-1", job_title="Engineer", company="Acme", portal="naukri",
        portal_job_id="pj-1", status=ApplicationStatus.applied, match_score=0.87,
        failure_reason=None, applied_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# list_applications
# ---------------------------------------------------------------------------

async def test_list_applications_returns_exact_body():
    row = _app_row()
    db = _RecordingTenantDB(results=[SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [row]))])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        result = await applications.list_applications(user=_user())

    assert result == [{
        "id": "app-1", "job_title": "Engineer", "company": "Acme", "portal": "naukri",
        "status": "applied", "match_score": 0.87, "applied_at": "2024-01-01T00:00:00+00:00",
    }]


async def test_list_applications_rejects_unknown_status():
    db = _RecordingTenantDB()

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        with pytest.raises(HTTPException) as exc:
            await applications.list_applications(application_status="bogus", user=_user())
    assert exc.value.status_code == 400
    assert db.executed == []


async def test_list_applications_filters_by_status_and_portal():
    db = _RecordingTenantDB(results=[SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        await applications.list_applications(
            application_status="applied", portal="naukri", limit=5, offset=10, user=_user()
        )

    sql = _sql(db.executed[0])
    assert "applications.status = 'applied'" in sql
    assert "applications.portal = 'naukri'" in sql
    assert "LIMIT 5" in sql
    assert "OFFSET 10" in sql


# ---------------------------------------------------------------------------
# get_application
# ---------------------------------------------------------------------------

async def test_get_application_404_when_missing():
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: None)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        with pytest.raises(HTTPException) as exc:
            await applications.get_application(application_id="missing", user=_user())
    assert exc.value.status_code == 404


async def test_get_application_returns_body_with_history():
    row = _app_row(failure_reason=ApplicationFailureReason.low_match_score)
    history_entry = SimpleNamespace(
        from_status="applying", to_status="applied", note="ok",
        recorded_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    db = _RecordingTenantDB(results=[
        SimpleNamespace(scalar_one_or_none=lambda: row),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [history_entry])),
    ])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        result = await applications.get_application(application_id="app-1", user=_user())

    assert result == {
        "id": "app-1", "job_title": "Engineer", "company": "Acme", "portal": "naukri",
        "portal_job_id": "pj-1", "status": "applied", "match_score": 0.87,
        "failure_reason": "low_match_score", "applied_at": "2024-01-01T00:00:00+00:00",
        "history": [{
            "from_status": "applying", "to_status": "applied", "note": "ok",
            "recorded_at": "2024-01-02T00:00:00+00:00",
        }],
    }


async def test_get_application_history_filters_by_application_id():
    row = _app_row()
    db = _RecordingTenantDB(results=[
        SimpleNamespace(scalar_one_or_none=lambda: row),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])),
    ])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        await applications.get_application(application_id="app-1", user=_user())

    sql = _sql(db.executed[1])
    assert "application_status_log.application_id = 'app-1'" in sql


# ---------------------------------------------------------------------------
# pause / resume 404 branches
# ---------------------------------------------------------------------------

async def test_pause_auto_apply_404_when_prefs_missing():
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: None)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        with pytest.raises(HTTPException) as exc:
            await applications.pause_auto_apply(body=applications.PauseRequest(minutes=30), user=_user())
    assert exc.value.status_code == 404
    assert db.commits == 0


async def test_resume_auto_apply_404_when_prefs_missing():
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: None)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        with pytest.raises(HTTPException) as exc:
            await applications.resume_auto_apply(user=_user())
    assert exc.value.status_code == 404
    assert db.commits == 0


# ---------------------------------------------------------------------------
# blacklist 404 branches and no-op-when-duplicate
# ---------------------------------------------------------------------------

async def test_add_company_blacklist_404_when_prefs_missing():
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: None)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        with pytest.raises(HTTPException) as exc:
            await applications.add_company_blacklist(
                body=applications.CompanyBlacklistRequest(name="Acme"), user=_user()
            )
    assert exc.value.status_code == 404


async def test_add_company_blacklist_is_noop_when_already_present():
    prefs = _prefs(company_blacklist=["Acme"])
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: prefs)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        result = await applications.add_company_blacklist(
            body=applications.CompanyBlacklistRequest(name="Acme"), user=_user()
        )

    assert result == {"ok": True}
    assert prefs.company_blacklist == ["Acme"]
    assert db.commits == 0


async def test_remove_company_blacklist_404_when_prefs_missing():
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: None)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        with pytest.raises(HTTPException) as exc:
            await applications.remove_company_blacklist(name="Acme", user=_user())
    assert exc.value.status_code == 404


async def test_add_title_blacklist_404_when_prefs_missing():
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: None)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        with pytest.raises(HTTPException) as exc:
            await applications.add_title_blacklist(
                body=applications.TitleBlacklistRequest(title="Dev"), user=_user()
            )
    assert exc.value.status_code == 404


async def test_add_title_blacklist_is_noop_when_already_present():
    prefs = _prefs(title_blacklist=["Dev"])
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: prefs)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        result = await applications.add_title_blacklist(
            body=applications.TitleBlacklistRequest(title="Dev"), user=_user()
        )

    assert result == {"ok": True}
    assert prefs.title_blacklist == ["Dev"]
    assert db.commits == 0


async def test_remove_title_blacklist_404_when_prefs_missing():
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: None)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        with pytest.raises(HTTPException) as exc:
            await applications.remove_title_blacklist(title="Dev", user=_user())
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# get_blacklists
# ---------------------------------------------------------------------------

async def test_get_blacklists_returns_empty_when_no_prefs():
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: None)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        result = await applications.get_blacklists(user=_user())

    assert result == {"companies": [], "titles": []}


async def test_get_blacklists_returns_stored_lists():
    prefs = _prefs(company_blacklist=["Acme"], title_blacklist=["Dev"])
    db = _RecordingTenantDB(results=[SimpleNamespace(scalar_one_or_none=lambda: prefs)])

    with patch.object(applications, "get_tenant_db", _tenant_gen(db)):
        result = await applications.get_blacklists(user=_user())

    assert result == {"companies": ["Acme"], "titles": ["Dev"]}


# ---------------------------------------------------------------------------
# delete_account
# ---------------------------------------------------------------------------

async def test_delete_account_rejects_unknown_mode():
    with pytest.raises(HTTPException) as exc:
        await applications.delete_account(
            body=applications.AccountDeletionRequest(mode="bogus"), user=_user(), db=object()
        )
    assert exc.value.status_code == 400


async def test_delete_account_delegates_to_execute_deletion():
    user = _user()
    db = object()
    captured = {}

    async def fake_execute_deletion(*, user, mode, db):
        captured["user"] = user
        captured["mode"] = mode
        captured["db"] = db
        return {"mode": "hard_delete", "message": "done"}

    with patch.object(applications, "execute_deletion", fake_execute_deletion):
        result = await applications.delete_account(
            body=applications.AccountDeletionRequest(mode="hard_delete"), user=user, db=db
        )

    assert result == {"mode": "hard_delete", "message": "done"}
    assert captured == {
        "user": user, "mode": applications.DeletionMode.hard_delete, "db": db,
    }
