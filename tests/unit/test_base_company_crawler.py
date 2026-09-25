"""
Characterization tests for app/crawlers/company_pages/base_company.py.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.crawlers.base import ApplicationReceipt, RawJob
from app.crawlers.company_pages.base_company import BaseCompanyCrawler
from tests.unit.crawler_fakes import FakeContext, FakePage


class _AcmeCrawler(BaseCompanyCrawler):
    portal_name = "acme"
    careers_url = "https://acme.example/careers"
    company_name = "Acme"

    def _parse_jobs(self, soup, keywords):
        return [
            RawJob(
                portal="acme",
                portal_job_id="1",
                title="Engineer",
                company="Acme",
                location="Remote",
                job_url="https://acme.example/careers/1",
            )
        ]

    async def apply(self, context, job, user_profile, resume_path=None, cover_letter=None):
        return ApplicationReceipt(success=False, requires_manual=True)


@pytest.fixture(autouse=True)
def _no_real_delays():
    with patch(
        "app.crawlers.anti_detection.human_delay", new=AsyncMock()
    ), patch("app.crawlers.anti_detection.random_scroll", new=AsyncMock()):
        yield


@pytest.mark.asyncio
async def test_search_jobs_returns_parsed_jobs_and_closes_page():
    page = FakePage(contents="<html></html>")
    context = FakeContext(pages_to_return=[page])
    crawler = _AcmeCrawler()

    jobs = await crawler.search_jobs(context, keywords=["python"])

    assert len(jobs) == 1
    assert jobs[0].portal_job_id == "1"
    assert page.closed is True


@pytest.mark.asyncio
async def test_search_jobs_returns_empty_list_on_navigation_error():
    page = FakePage(raise_on_goto=RuntimeError("timeout"))
    context = FakeContext(pages_to_return=[page])
    crawler = _AcmeCrawler()

    jobs = await crawler.search_jobs(context, keywords=["python"])

    assert jobs == []
    assert page.closed is True


@pytest.mark.asyncio
async def test_login_always_succeeds():
    crawler = _AcmeCrawler()
    assert await crawler.login(context=None) is True


@pytest.mark.asyncio
async def test_check_application_status_always_applied():
    crawler = _AcmeCrawler()
    assert await crawler.check_application_status(context=None, portal_application_id="x") == "applied"
