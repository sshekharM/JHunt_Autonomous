"""
Pin-down tests for app/routers/dashboard.py. Given a logged-in user calling
get_dashboard directly, then each stats bucket, the new-matches count, the
decrypted profile snippet, the recent-applications shape, and the missing-info
prompts are exactly what the dashboard UI relies on.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.routers import dashboard

pytestmark = pytest.mark.asyncio


def _user(schema="u_test"):
    return SimpleNamespace(id="user-001", schema_name=schema)


class _FakeTenantDB:
    def __init__(self, results):
        self._results = list(results)
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return self._results.pop(0)


def _tenant_gen(db):
    async def gen(schema_name):
        yield db
    return gen


def _empty_results():
    return [
        SimpleNamespace(fetchall=list),           # stats
        SimpleNamespace(scalar=lambda: None),            # new matches
        SimpleNamespace(first=lambda: None),              # profile
        SimpleNamespace(fetchall=list),             # recent applications
        SimpleNamespace(fetchall=list),             # missing info
    ]


async def test_get_dashboard_default_body_with_no_data():
    db = _FakeTenantDB(_empty_results())

    with patch.object(dashboard, "get_tenant_db", _tenant_gen(db)):
        result = await dashboard.get_dashboard(user=_user(), db=object())

    assert result == {
        "profile": {},
        "stats": {
            "total_applied": 0, "shortlisted": 0, "rejected": 0,
            "pending_hitl": 0, "failed": 0, "new_matches": 0,
        },
        "recent_applications": [],
        "missing_info_prompts": [],
    }


async def test_get_dashboard_buckets_each_status_correctly():
    results = _empty_results()
    results[0] = SimpleNamespace(fetchall=lambda: [
        ("applied", 3), ("shortlisted", 2), ("rejected", 1),
        ("pending_hitl", 4), ("failed_portal_error", 1),
        ("failed_low_match", 1), ("failed_missing_info", 1),
        ("withdrawn", 9),
    ])
    db = _FakeTenantDB(results)

    with patch.object(dashboard, "get_tenant_db", _tenant_gen(db)):
        result = await dashboard.get_dashboard(user=_user(), db=object())

    assert result["stats"] == {
        "total_applied": 3, "shortlisted": 2, "rejected": 1,
        "pending_hitl": 4, "failed": 3, "new_matches": 0,
    }


async def test_get_dashboard_reports_new_matches_count():
    results = _empty_results()
    results[1] = SimpleNamespace(scalar=lambda: 7)
    db = _FakeTenantDB(results)

    with patch.object(dashboard, "get_tenant_db", _tenant_gen(db)):
        result = await dashboard.get_dashboard(user=_user(), db=object())

    assert result["stats"]["new_matches"] == 7


async def test_get_dashboard_decrypts_profile_snippet():
    results = _empty_results()
    results[2] = SimpleNamespace(first=lambda: (b"enc", "Pune", "Engineer", 5))
    db = _FakeTenantDB(results)

    with patch.object(dashboard, "decrypt", lambda v: f"decrypted:{v}"):
        with patch.object(dashboard, "get_tenant_db", _tenant_gen(db)):
            result = await dashboard.get_dashboard(user=_user(), db=object())

    assert result["profile"] == {
        "full_name": "decrypted:b'enc'", "city": "Pune",
        "current_role": "Engineer", "years_experience": 5,
    }


async def test_get_dashboard_recent_applications_shape_and_rounding():
    results = _empty_results()
    results[3] = SimpleNamespace(fetchall=lambda: [
        ("Engineer", "Acme", "naukri", "applied", "2024-01-01", 0.8765),
        ("Analyst", "Beta", "linkedin", "applied", None, 0.5),
    ])
    db = _FakeTenantDB(results)

    with patch.object(dashboard, "get_tenant_db", _tenant_gen(db)):
        result = await dashboard.get_dashboard(user=_user(), db=object())

    assert result["recent_applications"] == [
        {
            "job_title": "Engineer", "company": "Acme", "portal": "naukri",
            "status": "applied", "applied_at": "2024-01-01", "match_score": 87.6,
        },
        {
            "job_title": "Analyst", "company": "Beta", "portal": "linkedin",
            "status": "applied", "applied_at": None, "match_score": 50.0,
        },
    ]


async def test_get_dashboard_missing_info_prompts():
    results = _empty_results()
    results[4] = SimpleNamespace(fetchall=lambda: [("phone", "Phone Number", "naukri")])
    db = _FakeTenantDB(results)

    with patch.object(dashboard, "get_tenant_db", _tenant_gen(db)):
        result = await dashboard.get_dashboard(user=_user(), db=object())

    assert result["missing_info_prompts"] == [
        {"field_name": "phone", "label": "Phone Number", "portal": "naukri"}
    ]


async def test_get_dashboard_new_matches_query_excludes_existing_applications():
    """Given the new-matches count query, when compiled, then it counts jobs with
    NO matching application row -- flipping NOT EXISTS to EXISTS would report
    already-applied jobs as new."""
    db = _FakeTenantDB(_empty_results())

    with patch.object(dashboard, "get_tenant_db", _tenant_gen(db)):
        await dashboard.get_dashboard(user=_user(), db=object())

    sql = str(db.executed[1])
    assert "NOT EXISTS" in sql
    assert "a.portal_job_id = j.portal_job_id" in sql


async def test_get_dashboard_missing_info_query_filters_unresolved_only():
    db = _FakeTenantDB(_empty_results())

    with patch.object(dashboard, "get_tenant_db", _tenant_gen(db)):
        await dashboard.get_dashboard(user=_user(), db=object())

    sql = str(db.executed[4])
    assert "resolved=false" in sql
