"""
Characterization tests for app/crawlers/shine.py.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.crawlers.base import RawJob
from app.crawlers.shine import ShineCrawler
from tests.unit.crawler_fakes import (
    ClickNavPage,
    FakeAsyncClient,
    FakeContext,
    FakeElement,
    FakePage,
    FakeResponse,
)

CARD_HTML = """
<article class="job-item">
  <h3><a href="/12345/">Engineer</a></h3>
  <span class="company-name">Acme</span>
  <span class="location">Pune</span>
  <span class="skill-tag">Python</span>
</article>
"""


@pytest.fixture(autouse=True)
def _patched_helpers():
    with patch("app.crawlers.shine.human_delay", new=AsyncMock()), \
            patch("app.crawlers.shine.micro_delay", new=AsyncMock()), \
            patch("app.crawlers.shine.random_scroll", new=AsyncMock()), \
            patch("app.crawlers.shine.human_type", new=AsyncMock()), \
            patch("app.crawlers.shine.audit") as audit_mock:
        yield audit_mock


@pytest.mark.asyncio
async def test_login_success_when_url_leaves_login():
    page = ClickNavPage(url_after_click="https://www.shine.com/dashboard")
    context = FakeContext(pages_to_return=[page])
    ok = await ShineCrawler().login(context)
    assert ok is True


@pytest.mark.asyncio
async def test_login_failure_when_still_on_login_url():
    page = ClickNavPage(url_after_click="https://www.shine.com/login/?error=1")
    context = FakeContext(pages_to_return=[page])
    ok = await ShineCrawler().login(context)
    assert ok is False


@pytest.mark.asyncio
async def test_login_logs_and_returns_false_when_close_fails_on_exception():
    class _BoomOnClose(FakePage):
        async def close(self):
            raise RuntimeError("already closed")

    page = _BoomOnClose(raise_on_goto=RuntimeError("net down"))
    context = FakeContext(pages_to_return=[page])

    with patch("app.crawlers.shine.logger") as mock_logger:
        ok = await ShineCrawler().login(context)

    assert ok is False
    mock_logger.warning.assert_called_once_with(
        "shine.page_close_failed", error="already closed"
    )


@pytest.mark.asyncio
async def test_search_jobs_uses_http_result_when_status_200():
    context = FakeContext(pages_to_return=[])
    fake_client = FakeAsyncClient(response=FakeResponse(status_code=200, text=CARD_HTML))
    with patch("app.crawlers.shine.httpx.AsyncClient", fake_client):
        jobs = await ShineCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1
    assert jobs[0].portal_job_id == "12345"
    assert jobs[0].skills_required == ["Python"]


@pytest.mark.asyncio
async def test_search_jobs_falls_back_to_playwright_on_http_exception():
    page = FakePage(contents=CARD_HTML)
    context = FakeContext(pages_to_return=[page])
    fake_client = FakeAsyncClient(raise_exc=RuntimeError("network down"))
    with patch("app.crawlers.shine.httpx.AsyncClient", fake_client):
        jobs = await ShineCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1
    assert page.closed is True


@pytest.mark.asyncio
async def test_playwright_search_returns_empty_list_on_navigation_error():
    page = FakePage(raise_on_goto=RuntimeError("boom"))
    context = FakeContext(pages_to_return=[page])
    jobs = await ShineCrawler()._playwright_search(context, "https://x", "India")
    assert jobs == []
    assert page.closed is True


def test_parse_search_html_skips_card_missing_title():
    html = '<article class="job-item"><span class="company-name">Acme</span></article>'
    jobs = ShineCrawler()._parse_search_html(html, "India")
    assert jobs == []


def test_parse_search_html_skips_one_malformed_card_but_keeps_others():
    two_cards = CARD_HTML + CARD_HTML.replace("12345", "67890")
    with patch("app.crawlers.shine.re.search", side_effect=[RuntimeError("bad regex"), None]):
        jobs = ShineCrawler()._parse_search_html(two_cards, "India")

    assert len(jobs) == 1
    assert "67890" in jobs[0].job_url


@pytest.mark.asyncio
async def test_apply_flags_manual_when_button_missing():
    page = FakePage()
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="shine", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await ShineCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.requires_manual is True


@pytest.mark.asyncio
async def test_apply_succeeds_and_submits_modal_when_present():
    apply_btn = FakeElement()
    submit_btn = FakeElement()
    modal = FakeElement(children={"button[type='submit'], .btn-apply, .submit-btn": submit_btn})
    page = FakePage(
        selectors={
            "a.apply-now, button.apply-now, .apply-btn, "
            "a[data-apply], button[data-label='Apply Now']": apply_btn,
            ".apply-modal, #applyModal, .modal-dialog": modal,
        }
    )
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="shine", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await ShineCrawler().apply(context, job, user_profile={})

    assert receipt.success is True
    assert submit_btn.clicked is True


@pytest.mark.asyncio
async def test_apply_returns_failure_receipt_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("timeout"))
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="shine", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await ShineCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.failure_reason == "timeout"


@pytest.mark.asyncio
async def test_check_application_status_always_applied():
    assert await ShineCrawler().check_application_status(context=None, portal_application_id="x") == "applied"
