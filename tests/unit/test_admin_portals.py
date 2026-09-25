"""
Pin-down tests for app/routers/admin/portals.py. Given the super-admin/ops-admin
calling the handlers directly, then the list response body, the 404 branch, and
the health-update mutation + audit call are exactly what the admin console relies on.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.portal_account import PortalAccountHealth
from app.routers.admin import portals as admin_portals

ADMIN = SimpleNamespace(id="admin-1")


@pytest.fixture
def audited(monkeypatch):
    calls = []
    monkeypatch.setattr(admin_portals, "audit", lambda event, **kw: calls.append((event, kw)))
    return calls


class _FakeDB:
    def __init__(self, accounts=None, account=None):
        self._accounts = accounts or []
        self._account = account
        self.commits = 0

    async def execute(self, stmt):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: self._accounts),
            scalar_one_or_none=lambda: self._account,
        )

    async def commit(self):
        self.commits += 1


def _account(portal="naukri", health=PortalAccountHealth.healthy, last_login=None, last_crawl=None):
    return SimpleNamespace(
        id="pa-1", portal=portal, health=health,
        last_login=last_login, last_crawl=last_crawl,
        is_active=True, notes="note",
    )


def test_list_portal_accounts_returns_exact_body_with_null_timestamps():
    acct = _account()
    db = _FakeDB(accounts=[acct])

    result = asyncio.run(admin_portals.list_portal_accounts(admin=ADMIN, db=db))

    assert result == [{
        "id": "pa-1", "portal": "naukri", "health": PortalAccountHealth.healthy,
        "last_login": None, "last_crawl": None,
        "is_active": True, "notes": "note",
    }]


def test_list_portal_accounts_stringifies_present_timestamps():
    acct = _account(last_login="2024-01-01", last_crawl="2024-01-02")
    db = _FakeDB(accounts=[acct])

    result = asyncio.run(admin_portals.list_portal_accounts(admin=ADMIN, db=db))

    assert result[0]["last_login"] == "2024-01-01"
    assert result[0]["last_crawl"] == "2024-01-02"


def test_update_portal_health_404_when_missing(audited):
    db = _FakeDB(account=None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            admin_portals.update_portal_health(
                "naukri", PortalAccountHealth.degraded, admin=ADMIN, db=db
            )
        )
    assert exc.value.status_code == 404
    assert db.commits == 0
    assert audited == []


def test_update_portal_health_updates_commits_and_audits(audited):
    acct = _account(health=PortalAccountHealth.healthy)
    db = _FakeDB(account=acct)

    result = asyncio.run(
        admin_portals.update_portal_health(
            "naukri", PortalAccountHealth.blocked, admin=ADMIN, db=db
        )
    )

    assert result == {"ok": True}
    assert acct.health == PortalAccountHealth.blocked
    assert db.commits == 1
    assert audited == [(
        "admin.portal_health_updated",
        {"admin_id": "admin-1", "details": {"portal": "naukri", "health": PortalAccountHealth.blocked}},
    )]


def test_update_portal_health_query_filters_by_portal():
    acct = _account()
    db = _FakeDB(account=acct)
    captured = []
    orig_execute = db.execute

    async def spying_execute(stmt):
        captured.append(stmt)
        return await orig_execute(stmt)

    db.execute = spying_execute
    asyncio.run(
        admin_portals.update_portal_health(
            "naukri", PortalAccountHealth.blocked, admin=ADMIN, db=db
        )
    )

    from sqlalchemy.dialects import postgresql
    sql = str(captured[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "system_portal_accounts.portal = 'naukri'" in sql
