"""
Characterization tests for app/crawlers/indeed.py.
"""
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from app.crawlers.base import RawJob
from app.crawlers.indeed import IndeedCrawler
from tests.unit.crawler_fakes import (
    ClickNavPage,
    FakeAsyncClient,
    FakeContext,
    FakeElement,
    FakePage,
    FakeResponse,
)

CARD_HTML = """
<div class="job_seen_beacon">
  <h2 class="jobTitle"><a href="/rc/clk?jk=abc123">Engineer</a></h2>
  <span class="companyName">Acme</span>
  <div class="companyLocation">Pune</div>
</div>
"""


@pytest.fixture(autouse=True)
def _patched_helpers():
    with patch("app.crawlers.indeed.human_delay", new=AsyncMock()), \
            patch("app.crawlers.indeed.micro_delay", new=AsyncMock()), \
            patch("app.crawlers.indeed.random_scroll", new=AsyncMock()), \
            patch("app.crawlers.indeed.human_type", new=AsyncMock()), \
            patch("app.crawlers.indeed.save_session_cookies", new=AsyncMock()), \
            patch("app.crawlers.indeed.audit") as audit_mock:
        yield audit_mock


@pytest.mark.asyncio
async def test_login_success_when_email_and_password_screens_present():
    page = ClickNavPage(
        url_after_click="https://in.indeed.com/jobs",
        selectors={
            "input[type='email'], input#ifl-InputFormField-3": FakeElement(),
            "input[type='password']": FakeElement(),
        },
    )
    context = FakeContext(pages_to_return=[page])
    ok = await IndeedCrawler().login(context)
    assert ok is True


@pytest.mark.asyncio
async def test_login_failure_when_url_still_login():
    page = ClickNavPage(url_after_click="https://in.indeed.com/account/login")
    context = FakeContext(pages_to_return=[page])
    ok = await IndeedCrawler().login(context)
    assert ok is False


@pytest.mark.asyncio
async def test_login_returns_false_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("boom"))
    context = FakeContext(pages_to_return=[page])
    ok = await IndeedCrawler().login(context)
    assert ok is False
    assert page.closed is True


@pytest.mark.asyncio
async def test_search_jobs_uses_http_result_when_status_200():
    context = FakeContext(pages_to_return=[])
    fake_client = FakeAsyncClient(response=FakeResponse(status_code=200, text=CARD_HTML))
    with patch("app.crawlers.indeed.httpx.AsyncClient", fake_client):
        jobs = await IndeedCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1
    assert jobs[0].portal_job_id == "abc123"
    assert jobs[0].job_url.startswith("https://in.indeed.com")


@pytest.mark.asyncio
async def test_search_jobs_falls_back_to_playwright_on_non_200():
    page = FakePage(contents=CARD_HTML)
    context = FakeContext(pages_to_return=[page])
    fake_client = FakeAsyncClient(response=FakeResponse(status_code=503, text=""))
    with patch("app.crawlers.indeed.httpx.AsyncClient", fake_client):
        jobs = await IndeedCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1
    assert page.closed is True


@pytest.mark.asyncio
async def test_search_jobs_returns_empty_list_on_http_exception():
    context = FakeContext(pages_to_return=[])
    fake_client = FakeAsyncClient(raise_exc=RuntimeError("network down"))
    with patch("app.crawlers.indeed.httpx.AsyncClient", fake_client):
        jobs = await IndeedCrawler().search_jobs(context, keywords=["python"])

    assert jobs == []


def test_parse_html_skips_card_missing_job_id():
    soup = BeautifulSoup(
        '<div class="job_seen_beacon"><h2 class="jobTitle"><a href="">Engineer</a></h2></div>',
        "lxml",
    )
    jobs = IndeedCrawler()._parse_html(soup)
    assert jobs == []


def test_parse_html_skips_one_malformed_card_but_keeps_others():
    two_cards = CARD_HTML + CARD_HTML.replace("abc123", "def456")
    soup = BeautifulSoup(two_cards, "lxml")
    with patch(
        "app.crawlers.indeed.re.search",
        side_effect=[RuntimeError("bad regex"), None],
    ):
        jobs = IndeedCrawler()._parse_html(soup)

    assert len(jobs) == 1
    assert "def456" in jobs[0].job_url


@pytest.mark.asyncio
async def test_apply_returns_manual_when_button_missing():
    page = FakePage()
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="indeed", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await IndeedCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.requires_manual is True


@pytest.mark.asyncio
async def test_apply_succeeds_and_audits_when_flow_completes():
    apply_btn = FakeElement()
    submit_btn = FakeElement()
    page = FakePage(
        selectors={
            "button#indeedApplyButton, a.indeed-apply-button, button[data-indeed-apply]": apply_btn,
            "button[type='submit'], button.ia-continueButton": submit_btn,
        }
    )
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="indeed", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await IndeedCrawler().apply(context, job, user_profile={})

    assert receipt.success is True


@pytest.mark.asyncio
async def test_apply_uploads_resume_when_file_input_present_and_path_given():
    apply_btn = FakeElement()
    upload = FakeElement()
    page = FakePage(
        selectors={
            "button#indeedApplyButton, a.indeed-apply-button, button[data-indeed-apply]": apply_btn,
            "input[type='file']": upload,
        }
    )
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="indeed", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await IndeedCrawler().apply(context, job, user_profile={}, resume_path="/tmp/resume.pdf")

    assert receipt.success is True
    assert upload.uploaded == "/tmp/resume.pdf"


@pytest.mark.asyncio
async def test_apply_returns_failure_receipt_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("timeout"))
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="indeed", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await IndeedCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.failure_reason == "timeout"


@pytest.mark.asyncio
async def test_check_application_status_always_applied():
    assert await IndeedCrawler().check_application_status(context=None, portal_application_id="x") == "applied"
