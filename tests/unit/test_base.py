"""
Characterization tests for app/crawlers/base.py -- BaseCrawler's concrete
helpers (RawJob/ApplicationReceipt DTOs, is_session_valid, skill extraction).
"""
import pytest

from app.crawlers.base import ApplicationReceipt, BaseCrawler, RawJob


class _ConcreteCrawler(BaseCrawler):
    """Minimal concrete subclass -- only the abstract methods are implemented,
    so tests exercise BaseCrawler's own concrete behaviour untouched."""

    portal_name = "concrete"

    async def login(self, context):
        return True

    async def search_jobs(self, context, keywords, location="India", page_num=1):
        return []

    async def apply(self, context, job, user_profile, resume_path=None, cover_letter=None):
        return ApplicationReceipt(success=True)

    async def check_application_status(self, context, portal_application_id):
        return "applied"


class _ContextWithPlainPages:
    """Mimics the real playwright.BrowserContext.pages contract: a plain,
    non-awaitable list property."""

    def __init__(self, pages: list):
        self.pages = pages


def test_raw_job_defaults():
    job = RawJob(
        portal="linkedin",
        portal_job_id="1",
        title="Engineer",
        company="Acme",
        location="Pune",
        job_url="https://x",
    )
    assert job.description == ""
    assert job.skills_required == []
    assert job.is_easy_apply is False
    assert job.extra == {}


def test_raw_job_default_factories_are_independent_instances():
    job_a = RawJob(portal="a", portal_job_id="1", title="t", company="c", location="l", job_url="u")
    job_b = RawJob(portal="b", portal_job_id="2", title="t", company="c", location="l", job_url="u")
    job_a.skills_required.append("python")
    assert job_b.skills_required == []


def test_application_receipt_defaults():
    receipt = ApplicationReceipt(success=False)
    assert receipt.portal_application_id is None
    assert receipt.failure_reason is None
    assert receipt.requires_manual is False
    assert receipt.missing_fields == []


@pytest.mark.asyncio
async def test_is_session_valid_true_when_pages_nonempty():
    """A real BrowserContext.pages is a plain, non-awaitable list."""
    crawler = _ConcreteCrawler()
    context = _ContextWithPlainPages(["p1", "p2"])
    assert await crawler.is_session_valid(context) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_is_session_valid_true_when_pages_empty():
    """Pins len(pages) >= 0, not > 0: an empty page list is still 'valid'."""
    crawler = _ConcreteCrawler()
    context = _ContextWithPlainPages([])
    assert await crawler.is_session_valid(context) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_is_session_valid_false_when_pages_attribute_missing():
    crawler = _ConcreteCrawler()

    class _NoPages:
        pass

    assert await crawler.is_session_valid(_NoPages()) is False  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_is_session_valid_false_when_pages_property_raises():
    """Any failure reading `.pages` (not just a missing attribute) is treated
    as an invalid session -- pins the intentionally broad except clause."""
    crawler = _ConcreteCrawler()

    class _BrokenPages:
        @property
        def pages(self):
            raise RuntimeError("context closed")

    assert await crawler.is_session_valid(_BrokenPages()) is False  # type: ignore[arg-type]


def test_extract_skills_from_text_matches_case_insensitively():
    crawler = _ConcreteCrawler()
    found = crawler._extract_skills_from_text(
        "Looking for a Python developer with SQL experience.",
        {"Python", "SQL", "Rust"},
    )
    assert set(found) == {"Python", "SQL"}


def test_extract_skills_from_text_returns_empty_when_no_match():
    crawler = _ConcreteCrawler()
    assert crawler._extract_skills_from_text("no relevant keywords here", {"Rust"}) == []
