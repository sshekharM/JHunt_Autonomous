"""
CHG-001 AC3 (crawl-task side) — crawl_portal accepts exactly the portals in
the shared crawler registry, and keeps no private portal map of its own.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.crawlers.registry import SUPPORTED_PORTALS
from app.tasks import crawl_jobs


def _run_crawl_portal(portal: str) -> tuple[object, bool]:
    """Invoke the task body with the async crawl stubbed out."""
    def fake_run(coro: object) -> dict:
        coro.close()  # type: ignore[attr-defined]
        return {"portal": portal, "status": "stubbed"}

    with patch.object(crawl_jobs.asyncio, "run", side_effect=fake_run) as run:
        result = crawl_jobs.crawl_portal.run(portal)
    return result, run.called


@pytest.mark.parametrize("portal", SUPPORTED_PORTALS)
def test_crawl_portal_accepts_every_registry_portal(portal: str) -> None:
    result, crawled = _run_crawl_portal(portal)

    assert crawled
    assert result == {"portal": portal, "status": "stubbed"}


def test_crawl_portal_rejects_unknown_portal_without_crawling() -> None:
    result, crawled = _run_crawl_portal("craigslist")

    assert not crawled
    assert result == {"error": "Unknown portal: craigslist"}


def test_crawl_portal_normalises_portal_name_case() -> None:
    with patch.object(crawl_jobs, "_run_crawl", new_callable=MagicMock) as run_crawl, \
            patch.object(crawl_jobs.asyncio, "run", return_value={"status": "stubbed"}):
        crawl_jobs.crawl_portal.run("Naukri")

    run_crawl.assert_called_once_with("naukri")


def test_is_known_portal_matches_the_registry() -> None:
    for portal in SUPPORTED_PORTALS:
        assert crawl_jobs.is_known_portal(portal)
    assert not crawl_jobs.is_known_portal("craigslist")


def test_crawl_jobs_has_no_private_portal_map() -> None:
    assert not hasattr(crawl_jobs, "_CRAWLER_MAP")
    assert not hasattr(crawl_jobs, "_import_crawler")


class _AccountLookupDb:
    """Fake AsyncSessionLocal() context manager that records the compiled SQL
    of the system-portal-account lookup and reports no active account, so
    _run_crawl returns immediately after that first query."""

    def __init__(self):
        self.statements: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        self.statements.append(str(stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )))
        return SimpleNamespace(scalar_one_or_none=lambda: None)


def test_run_crawl_account_lookup_filters_on_portal_active_and_not_blocked(monkeypatch):
    """Pins the system_portal_accounts WHERE clause (portal match, active,
    not blocked) so a flipped ==/!=/True->False in the filter is caught."""
    db = _AccountLookupDb()
    monkeypatch.setattr(crawl_jobs, "crawler_class_for", lambda name: MagicMock)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: db)

    result = asyncio.run(crawl_jobs._run_crawl("naukri"))

    assert result == {"portal": "naukri", "status": "skipped", "reason": "no_active_account"}
    sql = db.statements[0]
    assert "system_portal_accounts.portal = 'naukri'" in sql
    assert "system_portal_accounts.is_active IS true" in sql
    assert "system_portal_accounts.health != 'blocked'" in sql


class _FullCrawlDb:
    """Fake AsyncSessionLocal() used across a full _run_crawl pass: returns an
    active account on the first query, then accepts the final last_crawl
    UPDATE without inspection."""

    def __init__(self, account):
        self.account = account
        self.executed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *args, **kwargs):
        self.executed += 1
        if self.executed == 1:
            return SimpleNamespace(scalar_one_or_none=lambda: self.account)
        return SimpleNamespace()

    async def commit(self):
        pass


def test_run_crawl_falls_back_to_default_keyword_groups_when_none_configured(monkeypatch):
    """Pins `list(keyword_buckets.values()) or _DEFAULT_KEYWORD_GROUPS`: an
    empty taxonomy must still crawl every default keyword group (a stray
    `or->and` mutation would silently skip the whole crawl instead)."""
    account = SimpleNamespace()
    db = _FullCrawlDb(account)
    fake_crawler = SimpleNamespace(
        login=AsyncMock(return_value=True),
        search_jobs=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(crawl_jobs, "crawler_class_for", lambda name: lambda: fake_crawler)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: db)
    monkeypatch.setattr("app.crawlers.session_manager.get_context", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        "app.services.taxonomy_service.get_keyword_sets_for_crawling", AsyncMock(return_value={})
    )
    monkeypatch.setattr(crawl_jobs, "match_all_users", MagicMock())

    result = asyncio.run(crawl_jobs._run_crawl("naukri"))

    assert fake_crawler.search_jobs.await_count == len(crawl_jobs._DEFAULT_KEYWORD_GROUPS)
    assert result["portal"] == "naukri"
