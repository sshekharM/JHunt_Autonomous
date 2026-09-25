"""
Characterization tests for app/crawlers/glassdoor.py.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.crawlers.base import RawJob
from app.crawlers.glassdoor import GlassdoorCrawler
from tests.unit.crawler_fakes import ClickNavPage, FakeContext, FakeElement, FakePage


@pytest.fixture(autouse=True)
def _patched_helpers():
    with patch("app.crawlers.glassdoor.human_delay", new=AsyncMock()), \
            patch("app.crawlers.glassdoor.micro_delay", new=AsyncMock()), \
            patch("app.crawlers.glassdoor.random_scroll", new=AsyncMock()), \
            patch("app.crawlers.glassdoor.human_type", new=AsyncMock()), \
            patch("app.crawlers.glassdoor.save_session_cookies", new=AsyncMock()), \
            patch("app.crawlers.glassdoor.audit") as audit_mock:
        yield audit_mock


def _title_selector_card(title="Engineer", company="Acme", loc="Pune", href="/job/1?jobListingId=42"):
    return FakeElement(
        children={
            "a.jobLink span, a[data-test='job-title']": FakeElement(text=title),
            "div.jobHeader a, div.employer-name": FakeElement(text=company),
            "span.loc, div.location": FakeElement(text=loc),
            "a.jobLink, a[data-test='job-title']": FakeElement(attrs={"href": href}),
        }
    )


@pytest.mark.asyncio
async def test_login_success_when_redirected_to_profile():
    page = ClickNavPage(url_after_click="https://www.glassdoor.co.in/profile/index.htm")
    context = FakeContext(pages_to_return=[page])
    ok = await GlassdoorCrawler().login(context)
    assert ok is True
    assert page.closed is True


@pytest.mark.asyncio
async def test_login_success_when_on_domain_without_profile_or_login_in_url():
    page = ClickNavPage(url_after_click="https://www.glassdoor.co.in/home")
    context = FakeContext(pages_to_return=[page])
    ok = await GlassdoorCrawler().login(context)
    assert ok is True


@pytest.mark.asyncio
async def test_login_failure_when_still_on_login_page():
    page = ClickNavPage(url_after_click="https://www.glassdoor.co.in/login/error")
    context = FakeContext(pages_to_return=[page])
    ok = await GlassdoorCrawler().login(context)
    assert ok is False


@pytest.mark.asyncio
async def test_login_returns_false_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("boom"))
    context = FakeContext(pages_to_return=[page])
    ok = await GlassdoorCrawler().login(context)
    assert ok is False
    assert page.closed is True


@pytest.mark.asyncio
async def test_search_jobs_parses_cards_into_raw_jobs():
    card = _title_selector_card()
    page = FakePage(selectors={"li.react-job-listing, div[data-test='jobListing']": [card]})
    context = FakeContext(pages_to_return=[page])

    jobs = await GlassdoorCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1
    assert jobs[0].portal == "glassdoor"
    assert jobs[0].portal_job_id == "42"
    assert jobs[0].title == "Engineer"
    assert jobs[0].job_url == "https://www.glassdoor.co.in/job/1?jobListingId=42"


@pytest.mark.asyncio
async def test_search_jobs_skips_cards_that_fail_to_parse_and_continues():
    good = _title_selector_card()
    bad = FakeElement(children={})  # no title element -> _parse_card returns None
    page = FakePage(selectors={"li.react-job-listing, div[data-test='jobListing']": [bad, good]})
    context = FakeContext(pages_to_return=[page])

    jobs = await GlassdoorCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_search_jobs_returns_empty_list_on_navigation_error():
    page = FakePage(raise_on_goto=RuntimeError("net"))
    context = FakeContext(pages_to_return=[page])

    jobs = await GlassdoorCrawler().search_jobs(context, keywords=["python"])

    assert jobs == []
    assert page.closed is True


@pytest.mark.asyncio
async def test_parse_card_returns_none_when_title_missing():
    crawler = GlassdoorCrawler()
    card = FakeElement(children={})
    assert await crawler._parse_card(card) is None


@pytest.mark.asyncio
async def test_parse_card_returns_none_on_internal_exception():
    crawler = GlassdoorCrawler()

    class _Boom(FakeElement):
        async def query_selector(self, sel):
            raise RuntimeError("dom error")

    assert await crawler._parse_card(_Boom()) is None


@pytest.mark.asyncio
async def test_parse_card_absolute_href_kept_as_is():
    crawler = GlassdoorCrawler()
    card = _title_selector_card(href="https://external.example/job/9")
    job = await crawler._parse_card(card)
    assert isinstance(job, RawJob)
    assert job.job_url == "https://external.example/job/9"


@pytest.mark.asyncio
async def test_apply_flags_manual_when_apply_button_missing():
    page = FakePage(selectors={})
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="glassdoor", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await GlassdoorCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.requires_manual is True
    assert receipt.failure_reason == "apply_button_not_found"


@pytest.mark.asyncio
async def test_apply_flags_manual_when_redirects_externally():
    apply_btn = FakeElement()
    page = FakePage(
        selectors={"button[data-test='applyButton'], a.apply-btn": apply_btn},
        nav_url="https://external-ats.example/apply",
    )
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="glassdoor", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await GlassdoorCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.failure_reason == "redirects_to_external_ats"


@pytest.mark.asyncio
async def test_apply_succeeds_when_navigation_stays_on_glassdoor():
    apply_btn = FakeElement()
    page = FakePage(
        selectors={"button[data-test='applyButton'], a.apply-btn": apply_btn},
        nav_url="https://www.glassdoor.co.in/apply/confirm",
    )
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="glassdoor", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await GlassdoorCrawler().apply(context, job, user_profile={})

    assert receipt.success is True


@pytest.mark.asyncio
async def test_apply_returns_failure_receipt_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("timeout"))
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="glassdoor", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await GlassdoorCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.requires_manual is True
    assert receipt.failure_reason == "timeout"


@pytest.mark.asyncio
async def test_check_application_status_is_always_applied():
    assert await GlassdoorCrawler().check_application_status(context=None, portal_application_id="x") == "applied"
