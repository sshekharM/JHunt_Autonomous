"""
Characterization tests for app/crawlers/monster.py.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.crawlers.base import RawJob
from app.crawlers.monster import MonsterCrawler
from tests.unit.crawler_fakes import (
    ClickNavPage,
    FakeAsyncClient,
    FakeContext,
    FakeElement,
    FakePage,
    FakeResponse,
)

CARD_HTML = """
<div class="job-card">
  <a class="job-tittle" href="/job/123456">Engineer</a>
  <span class="company-name">Acme</span>
  <span class="location">Pune</span>
  <span class="tag">Python</span>
</div>
"""


@pytest.fixture(autouse=True)
def _patched_helpers():
    with patch("app.crawlers.monster.human_delay", new=AsyncMock()), \
            patch("app.crawlers.monster.micro_delay", new=AsyncMock()), \
            patch("app.crawlers.monster.random_scroll", new=AsyncMock()), \
            patch("app.crawlers.monster.human_type", new=AsyncMock()), \
            patch("app.crawlers.monster.audit") as audit_mock:
        yield audit_mock


@pytest.mark.asyncio
async def test_login_success_when_url_leaves_login():
    page = ClickNavPage(url_after_click="https://www.monsterindia.com/dashboard")
    context = FakeContext(pages_to_return=[page])
    ok = await MonsterCrawler().login(context)
    assert ok is True


@pytest.mark.asyncio
async def test_login_failure_when_still_on_login_url():
    page = ClickNavPage(url_after_click="https://www.monsterindia.com/login?error=1")
    context = FakeContext(pages_to_return=[page])
    ok = await MonsterCrawler().login(context)
    assert ok is False


@pytest.mark.asyncio
async def test_login_logs_and_returns_false_when_close_fails_on_exception():
    class _BoomOnClose(FakePage):
        async def close(self):
            raise RuntimeError("already closed")

    page = _BoomOnClose(raise_on_goto=RuntimeError("net down"))
    context = FakeContext(pages_to_return=[page])

    with patch("app.crawlers.monster.logger") as mock_logger:
        ok = await MonsterCrawler().login(context)

    assert ok is False
    mock_logger.warning.assert_called_once_with(
        "monster.page_close_failed", error="already closed"
    )


@pytest.mark.asyncio
async def test_search_jobs_uses_http_result_when_status_200():
    context = FakeContext(pages_to_return=[])
    fake_client = FakeAsyncClient(response=FakeResponse(status_code=200, text=CARD_HTML))
    with patch("app.crawlers.monster.httpx.AsyncClient", fake_client):
        jobs = await MonsterCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1
    assert jobs[0].portal_job_id == "123456"
    assert jobs[0].skills_required == ["Python"]


@pytest.mark.asyncio
async def test_search_jobs_falls_back_to_playwright_on_http_exception():
    page = FakePage(contents=CARD_HTML)
    context = FakeContext(pages_to_return=[page])
    fake_client = FakeAsyncClient(raise_exc=RuntimeError("network down"))
    with patch("app.crawlers.monster.httpx.AsyncClient", fake_client):
        jobs = await MonsterCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1
    assert page.closed is True


@pytest.mark.asyncio
async def test_playwright_search_returns_empty_list_on_navigation_error():
    page = FakePage(raise_on_goto=RuntimeError("boom"))
    context = FakeContext(pages_to_return=[page])
    jobs = await MonsterCrawler()._playwright_search(context, "https://x", "India")
    assert jobs == []
    assert page.closed is True


def test_parse_search_html_skips_card_missing_title():
    soup_html = '<div class="job-card"><span class="company-name">Acme</span></div>'
    jobs = MonsterCrawler()._parse_search_html(soup_html, "India")
    assert jobs == []


def test_parse_search_html_skips_one_malformed_card_but_keeps_others():
    two_cards = CARD_HTML + CARD_HTML.replace("123456", "654321")
    with patch("app.crawlers.monster.re.search", side_effect=[RuntimeError("bad regex"), None]):
        jobs = MonsterCrawler()._parse_search_html(two_cards, "India")

    assert len(jobs) == 1
    assert "654321" in jobs[0].job_url


@pytest.mark.asyncio
async def test_apply_flags_manual_when_button_missing():
    page = FakePage()
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="monster", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await MonsterCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.requires_manual is True


@pytest.mark.asyncio
async def test_apply_succeeds_and_submits_modal_when_present():
    apply_btn = FakeElement()
    submit_btn = FakeElement()
    modal = FakeElement(children={"button[type='submit'], .submit-apply, button.apply": submit_btn})
    page = FakePage(
        selectors={
            "button.apply-btn, a.apply-btn, button[data-action='apply'], "
            "button.applyButton, a.applyButton, .apply-now-btn": apply_btn,
            ".apply-modal, #applyModal, .modal.show": modal,
        }
    )
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="monster", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await MonsterCrawler().apply(context, job, user_profile={})

    assert receipt.success is True
    assert submit_btn.clicked is True


@pytest.mark.asyncio
async def test_apply_returns_failure_receipt_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("timeout"))
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="monster", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await MonsterCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.failure_reason == "timeout"


@pytest.mark.asyncio
async def test_check_application_status_always_applied():
    assert await MonsterCrawler().check_application_status(context=None, portal_application_id="x") == "applied"
