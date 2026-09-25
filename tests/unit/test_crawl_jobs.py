"""
CHG-001 AC3 (crawl-task side) — crawl_portal accepts exactly the portals in
the shared crawler registry, and keeps no private portal map of its own.
"""
from unittest.mock import MagicMock, patch

import pytest

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
