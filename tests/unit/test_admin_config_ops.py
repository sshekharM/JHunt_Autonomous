"""
Pin-down tests for admin config/ops handlers and the settings they read.
Given an admin calling the handler directly, then the response, the settings
mutation, and the SQL filters are exactly what the admin console relies on.
"""
import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.config import Settings, settings
from app.routers.admin import config as admin_config
from app.routers.admin import ops as admin_ops

ADMIN = SimpleNamespace(id="admin-1")


@pytest.fixture
def audited(monkeypatch):
    calls = []
    monkeypatch.setattr(admin_config, "audit", lambda event, **kw: calls.append((event, kw)))
    return calls


def test_update_config_applies_values_audits_and_returns_ok(monkeypatch, audited):
    monkeypatch.setattr(settings, "crawl_interval_hours", 1)
    monkeypatch.setattr(settings, "crawl_max_concurrency", 1)
    body = admin_config.SystemConfigUpdate(crawl_interval_hours=6, crawl_max_concurrency=3)

    result = asyncio.run(admin_config.update_config(body, admin=ADMIN))

    assert result == {"ok": True}
    assert (settings.crawl_interval_hours, settings.crawl_max_concurrency) == (6, 3)
    assert audited == [("admin.config_updated", {
        "admin_id": "admin-1",
        "details": {"crawl_interval_hours": 6, "crawl_max_concurrency": 3},
    })]


def test_update_config_leaves_unset_values_untouched(monkeypatch, audited):
    monkeypatch.setattr(settings, "crawl_interval_hours", 4)
    monkeypatch.setattr(settings, "crawl_max_concurrency", 2)

    asyncio.run(admin_config.update_config(admin_config.SystemConfigUpdate(), admin=ADMIN))

    assert (settings.crawl_interval_hours, settings.crawl_max_concurrency) == (4, 2)


def test_get_config_reports_current_settings():
    result = asyncio.run(admin_config.get_config(admin=ADMIN))
    assert result == {
        "crawl_interval_hours": settings.crawl_interval_hours,
        "crawl_max_concurrency": settings.crawl_max_concurrency,
        "app_env": settings.app_env,
    }


class _RecordingDB:
    """Stands in for AsyncSession; records every statement the dashboard runs."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(scalar=lambda: 0, scalars=lambda: SimpleNamespace(all=list))


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_ops_dashboard_counts_only_active_and_onboarded_users():
    db = _RecordingDB()
    asyncio.run(admin_ops.ops_dashboard(admin=ADMIN, db=db))
    active_sql, onboarded_sql = _sql(db.statements[1]), _sql(db.statements[2])
    assert "users.is_active = true" in active_sql
    assert "users.onboarding_complete = true" in onboarded_sql


def test_is_production_only_for_production_env():
    assert Settings(app_env="production").is_production is True
    assert Settings(app_env="development").is_production is False


def test_minio_secure_defaults_off(monkeypatch):
    monkeypatch.delenv("MINIO_SECURE", raising=False)
    assert Settings(_env_file=None).minio_secure is False
