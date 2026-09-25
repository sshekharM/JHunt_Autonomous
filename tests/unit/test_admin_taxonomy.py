"""
Pin-down tests for app/routers/admin/taxonomy.py. Given a content-admin calling
the handlers directly, then the pending-skills list body, the action validation,
the UPDATE predicate/COALESCE fallback, and the audit event name are exactly what
the taxonomy review console relies on.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.routers.admin import taxonomy as admin_taxonomy

ADMIN = SimpleNamespace(id="admin-1")


@pytest.fixture
def audited(monkeypatch):
    calls = []
    monkeypatch.setattr(admin_taxonomy, "audit", lambda event, **kw: calls.append((event, kw)))
    return calls


class _FakeDB:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.executed = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        self.executed.append((stmt, params))
        return SimpleNamespace(fetchall=lambda: self._rows)

    async def commit(self):
        self.commits += 1


def _sql_bound(stmt, params):
    bound = stmt.bindparams(**params) if params else stmt
    return str(bound.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_list_pending_skills_returns_exact_body():
    db = _FakeDB(rows=[("sk-1", "Python", "backend", "resume", "dev-tools")])

    result = asyncio.run(admin_taxonomy.list_pending_skills(admin=ADMIN, db=db))

    assert result == [{
        "id": "sk-1", "skill_name": "Python", "category": "backend",
        "source": "resume", "suggested_category": "dev-tools",
    }]


def test_list_pending_skills_filters_on_pending_review_status():
    db = _FakeDB()
    asyncio.run(admin_taxonomy.list_pending_skills(admin=ADMIN, db=db))
    stmt, _ = db.executed[0]
    assert "status='pending_review'" in str(stmt)


def test_review_skill_rejects_unknown_action():
    data = admin_taxonomy.SkillReviewAction(skill_id="sk-1", action="delete")
    db = _FakeDB()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(admin_taxonomy.review_skill(data, admin=ADMIN, db=db))
    assert exc.value.status_code == 400
    assert db.executed == []
    assert db.commits == 0


def test_review_skill_approve_sets_active_and_audits(audited):
    data = admin_taxonomy.SkillReviewAction(skill_id="sk-1", action="approve", category="backend")
    db = _FakeDB()

    result = asyncio.run(admin_taxonomy.review_skill(data, admin=ADMIN, db=db))

    assert result == {"ok": True, "status": "active"}
    assert db.commits == 1
    stmt, params = db.executed[0]
    assert params == {"s": "active", "cat": "backend", "id": "sk-1"}
    assert audited == [(
        "admin.taxonomy.skill_approved",
        {"admin_id": "admin-1", "details": {"skill_id": "sk-1", "category": "backend"}},
    )]


def test_review_skill_reject_sets_rejected_status():
    data = admin_taxonomy.SkillReviewAction(skill_id="sk-2", action="reject")
    db = _FakeDB()

    result = asyncio.run(admin_taxonomy.review_skill(data, admin=ADMIN, db=db))

    assert result == {"ok": True, "status": "rejected"}
    _, params = db.executed[0]
    assert params == {"s": "rejected", "cat": "", "id": "sk-2"}


def test_review_skill_empty_category_falls_back_to_existing_category():
    """Given an empty category string, when the UPDATE runs, then COALESCE(NULLIF(...))
    leaves the stored category untouched -- flipping either function would instead
    null it out or overwrite it with the empty string."""
    data = admin_taxonomy.SkillReviewAction(skill_id="sk-1", action="approve", category="")
    db = _FakeDB()

    asyncio.run(admin_taxonomy.review_skill(data, admin=ADMIN, db=db))

    stmt, params = db.executed[0]
    sql = _sql_bound(stmt, params)
    assert "COALESCE(NULLIF('',''), category)" in sql
    assert "id='sk-1'" in sql
