"""
Pin-down tests for app/routers/admin/users.py. Given a super-admin/support-admin
calling the handlers directly, then the list response body, the 404 branches, the
suspend/delete mutations, and the audit calls are exactly what the admin console
relies on.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.routers.admin import users as admin_users

ADMIN = SimpleNamespace(id="admin-1")


@pytest.fixture
def audited(monkeypatch):
    calls = []
    monkeypatch.setattr(admin_users, "audit", lambda event, **kw: calls.append((event, kw)))
    return calls


class _FakeDB:
    def __init__(self, rows=None, user=None):
        self._rows = rows or []
        self._user = user
        self.commits = 0
        self.deleted = []
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return SimpleNamespace(
            fetchall=lambda: self._rows,
            scalar_one_or_none=lambda: self._user,
        )

    async def commit(self):
        self.commits += 1

    async def delete(self, obj):
        self.deleted.append(obj)


def test_list_users_returns_exact_body():
    row = ("u1", "hash1", "tp1", "google", True, False, "free", "2024-01-01T00:00:00")
    db = _FakeDB(rows=[row])

    result = asyncio.run(admin_users.list_users(admin=ADMIN, db=db))

    assert result == [{
        "id": "u1", "email_hash": "hash1", "thumbprint": "tp1",
        "oauth_provider": "google", "is_active": True,
        "onboarding_complete": False, "tier": "free",
        "created_at": "2024-01-01T00:00:00",
    }]


def test_suspend_user_404_when_missing(audited):
    db = _FakeDB(user=None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(admin_users.suspend_user("u1", admin=ADMIN, db=db))
    assert exc.value.status_code == 404
    assert db.commits == 0
    assert audited == []


def test_suspend_user_deactivates_commits_and_audits(audited):
    user = SimpleNamespace(id="u1", is_active=True)
    db = _FakeDB(user=user)

    result = asyncio.run(admin_users.suspend_user("u1", admin=ADMIN, db=db))

    assert result == {"ok": True}
    assert user.is_active is False
    assert db.commits == 1
    assert audited == [("admin.user_suspended", {"admin_id": "admin-1", "resource": "u1"})]


def test_suspend_user_query_filters_by_user_id():
    user = SimpleNamespace(id="u1", is_active=True)
    db = _FakeDB(user=user)
    asyncio.run(admin_users.suspend_user("u1", admin=ADMIN, db=db))
    sql = str(db.executed[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "users.id = 'u1'" in sql


def test_delete_user_404_when_missing(audited):
    db = _FakeDB(user=None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(admin_users.delete_user("u1", admin=ADMIN, db=db))
    assert exc.value.status_code == 404
    assert db.deleted == []
    assert db.commits == 0
    assert audited == []


def test_delete_user_deletes_commits_and_audits(audited):
    user = SimpleNamespace(id="u1")
    db = _FakeDB(user=user)

    result = asyncio.run(admin_users.delete_user("u1", admin=ADMIN, db=db))

    assert result == {"ok": True}
    assert db.deleted == [user]
    assert db.commits == 1
    assert audited == [("admin.user_deleted", {"admin_id": "admin-1", "resource": "u1"})]
