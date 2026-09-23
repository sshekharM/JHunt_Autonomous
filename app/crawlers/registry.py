"""
Single source of truth mapping portal names to crawler classes.

Used by both the crawl task (app.tasks.crawl_jobs) and the apply/status paths
(app.services.application_service) so that every portal we crawl can also be
applied to. Crawler modules are imported lazily to keep Playwright out of
import time.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # base.py imports Playwright; keep it out of import time
    from app.crawlers.base import BaseCrawler

_REGISTRY: dict[str, tuple[str, str]] = {
    "naukri": ("app.crawlers.naukri", "NaukriCrawler"),
    "linkedin": ("app.crawlers.linkedin", "LinkedInCrawler"),
    "glassdoor": ("app.crawlers.glassdoor", "GlassdoorCrawler"),
    "indeed": ("app.crawlers.indeed", "IndeedCrawler"),
    "monster": ("app.crawlers.monster", "MonsterCrawler"),
    "shine": ("app.crawlers.shine", "ShineCrawler"),
}

SUPPORTED_PORTALS: tuple[str, ...] = tuple(_REGISTRY)


def is_supported(portal: str) -> bool:
    """True if a crawler is registered for this portal (case-insensitive)."""
    return portal.lower() in _REGISTRY


def crawler_class_for(portal: str) -> type[BaseCrawler]:
    """Import and return the crawler class for a portal; ValueError if unknown."""
    entry = _REGISTRY.get(portal.lower())
    if entry is None:
        raise ValueError(f"No crawler registered for portal: {portal!r}")
    module_path, class_name = entry
    crawler_cls: type[BaseCrawler] = getattr(importlib.import_module(module_path), class_name)
    return crawler_cls


def crawler_for(portal: str) -> BaseCrawler:
    """Return a fresh crawler instance for a portal; ValueError if unknown."""
    return crawler_class_for(portal)()
