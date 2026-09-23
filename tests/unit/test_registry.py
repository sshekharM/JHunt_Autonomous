"""
CHG-001 — every portal that is crawled on the beat schedule can be applied to.
"""
import subprocess
import sys
from pathlib import Path

import pytest


def _scheduled_crawl_portals() -> set[str]:
    from app.tasks.celery_app import celery_app

    return {
        entry["args"][0]
        for entry in celery_app.conf.beat_schedule.values()
        if entry["task"] == "app.tasks.crawl_jobs.crawl_portal"
    }


# AC1 — every scheduled crawl portal resolves on the apply path
@pytest.mark.parametrize("portal", sorted(_scheduled_crawl_portals()))
def test_every_scheduled_crawl_portal_can_be_applied_to(portal: str) -> None:
    from app.crawlers.base import BaseCrawler
    from app.services.application_service import _crawler_for_portal

    crawler = _crawler_for_portal(portal)

    assert isinstance(crawler, BaseCrawler)
    assert crawler.portal_name == portal


# AC2 — Monster and Shine resolve to their concrete crawlers
def test_monster_and_shine_resolve_to_their_crawlers() -> None:
    from app.crawlers.monster import MonsterCrawler
    from app.crawlers.shine import ShineCrawler
    from app.services.application_service import _crawler_for_portal

    assert isinstance(_crawler_for_portal("monster"), MonsterCrawler)
    assert isinstance(_crawler_for_portal("shine"), ShineCrawler)


# AC3 — the registry covers every scheduled crawl portal (crawl-task side:
# tests/unit/test_crawl_jobs.py)
def test_registry_covers_every_scheduled_crawl_portal() -> None:
    from app.crawlers.registry import SUPPORTED_PORTALS

    assert _scheduled_crawl_portals() <= set(SUPPORTED_PORTALS)


def test_registry_resolves_classes_without_instantiating() -> None:
    from app.crawlers.registry import crawler_class_for, is_supported
    from app.crawlers.shine import ShineCrawler

    assert crawler_class_for("SHINE") is ShineCrawler
    assert is_supported("Shine")
    assert not is_supported("craigslist")
    with pytest.raises(ValueError, match="craigslist"):
        crawler_class_for("craigslist")


# AC4 — case-insensitive lookup; unknown portal still rejected
def test_lookup_is_case_insensitive() -> None:
    from app.crawlers.monster import MonsterCrawler
    from app.services.application_service import _crawler_for_portal

    assert isinstance(_crawler_for_portal("Monster"), MonsterCrawler)


def test_unknown_portal_raises_value_error() -> None:
    from app.services.application_service import _crawler_for_portal

    with pytest.raises(ValueError, match="craigslist"):
        _crawler_for_portal("craigslist")


# AC5 — registry import pulls in neither crawler modules nor Playwright.
# Checked in a fresh interpreter so this session's module identity is untouched.
def test_registry_import_is_lazy() -> None:
    probe = (
        "import sys, app.crawlers.registry; "
        "loaded = [m for m in sys.modules "
        "if m.split('.')[0] == 'playwright' "
        "or m in ('app.crawlers.base', 'app.crawlers.monster', 'app.crawlers.naukri')]; "
        "print(','.join(loaded))"
    )
    root = Path(__file__).resolve().parents[2]
    out = subprocess.run(
        [sys.executable, "-c", probe], cwd=root, capture_output=True, text=True, check=True
    )

    assert out.stdout.strip() == ""
