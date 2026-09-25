"""
Characterization tests for app/crawlers/naukri.py.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.crawlers.base import RawJob
from app.crawlers.naukri import NaukriCrawler
from tests.unit.crawler_fakes import (
    ClickNavPage,
    FakeAsyncClient,
    FakeContext,
    FakeElement,
    FakePage,
    FakeResponse,
)

API_RESPONSE = {
    "jobDetails": [
        {
            "jobId": "111",
            "title": "Engineer",
            "companyName": "Acme",
            "placeholders": [{"label": "3-5 Yrs"}, {"label": "10-15 Lacs"}],
            "jdURL": "https://www.naukri.com/job/111",
            "jobDescription": "desc",
            "tagsAndSkills": [{"label": "Python"}],
        }
    ]
}


@pytest.fixture(autouse=True)
def _patched_helpers():
    with patch("app.crawlers.naukri.human_delay", new=AsyncMock()), \
            patch("app.crawlers.naukri.micro_delay", new=AsyncMock()), \
            patch("app.crawlers.naukri.random_scroll", new=AsyncMock()), \
            patch("app.crawlers.naukri.human_type", new=AsyncMock()), \
            patch("app.crawlers.naukri.save_session_cookies", new=AsyncMock()), \
            patch("app.crawlers.naukri.audit") as audit_mock:
        yield audit_mock


@pytest.mark.asyncio
async def test_login_success_when_url_leaves_login():
    accept_btn = FakeElement()
    page = ClickNavPage(
        url_after_click="https://www.naukri.com/mnjuser/homepage",
        selectors={"button#onetrust-accept-btn-handler": accept_btn},
    )
    context = FakeContext(pages_to_return=[page])
    ok = await NaukriCrawler().login(context)
    assert ok is True


@pytest.mark.asyncio
async def test_login_continues_when_cookie_banner_absent():
    """Pins the swallowed cookie-banner-click exception: login still proceeds."""
    page = ClickNavPage(url_after_click="https://www.naukri.com/mnjuser/homepage")
    context = FakeContext(pages_to_return=[page])
    ok = await NaukriCrawler().login(context)
    assert ok is True


@pytest.mark.asyncio
async def test_login_failure_when_still_on_login_url():
    page = ClickNavPage(url_after_click="https://www.naukri.com/nlogin/login.php?error=1")
    context = FakeContext(pages_to_return=[page])
    ok = await NaukriCrawler().login(context)
    assert ok is False


@pytest.mark.asyncio
async def test_login_returns_false_and_swallows_close_error_on_exception():
    class _BoomOnClose(FakePage):
        async def close(self):
            raise RuntimeError("already closed")

    page = _BoomOnClose(raise_on_goto=RuntimeError("net down"))
    context = FakeContext(pages_to_return=[page])

    ok = await NaukriCrawler().login(context)

    assert ok is False


@pytest.mark.asyncio
async def test_search_jobs_uses_api_result_when_status_200():
    context = FakeContext(pages_to_return=[])
    fake_client = FakeAsyncClient(response=FakeResponse(status_code=200, json_data=API_RESPONSE))
    with patch("app.crawlers.naukri.httpx.AsyncClient", fake_client):
        jobs = await NaukriCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1
    assert jobs[0].portal_job_id == "111"
    assert jobs[0].skills_required == ["Python"]


@pytest.mark.asyncio
async def test_search_jobs_falls_back_to_scrape_on_non_200():
    page = FakePage(contents="")
    context = FakeContext(pages_to_return=[page])
    fake_client = FakeAsyncClient(response=FakeResponse(status_code=500))
    with patch("app.crawlers.naukri.httpx.AsyncClient", fake_client):
        jobs = await NaukriCrawler().search_jobs(context, keywords=["python"])

    assert jobs == []
    assert page.closed is True


@pytest.mark.asyncio
async def test_search_jobs_returns_empty_list_on_exception():
    context = FakeContext(pages_to_return=[])
    fake_client = FakeAsyncClient(raise_exc=RuntimeError("network down"))
    with patch("app.crawlers.naukri.httpx.AsyncClient", fake_client):
        jobs = await NaukriCrawler().search_jobs(context, keywords=["python"])

    assert jobs == []


def test_parse_api_response_skips_item_missing_job_id():
    jobs = NaukriCrawler()._parse_api_response({"jobDetails": [{"title": "t"}]})
    assert jobs == []


def test_parse_api_response_warns_and_skips_on_malformed_item():
    jobs = NaukriCrawler()._parse_api_response({"jobDetails": [{"placeholders": "not-a-list"}]})
    assert jobs == []


@pytest.mark.asyncio
async def test_scrape_search_page_returns_empty_list_on_navigation_error():
    page = FakePage(raise_on_goto=RuntimeError("boom"))
    context = FakeContext(pages_to_return=[page])
    jobs = await NaukriCrawler()._scrape_search_page(context, "python", "India", 1)
    assert jobs == []
    assert page.closed is True


@pytest.mark.asyncio
async def test_apply_flags_manual_when_button_missing():
    page = FakePage()
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="naukri", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await NaukriCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.requires_manual is True


@pytest.mark.asyncio
async def test_apply_flags_manual_when_screening_questions_unanswered():
    apply_btn = FakeElement()
    question = FakeElement(text="Notice period?")
    page = FakePage(
        selectors={
            "button#apply-button, a#apply-button, button.apply-button": apply_btn,
            "div.screening-question, div.assessment-question": [question],
        }
    )
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="naukri", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await NaukriCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.failure_reason == "unanswered_screening_questions"


@pytest.mark.asyncio
async def test_apply_succeeds_when_no_screening_questions():
    apply_btn = FakeElement()
    submit_btn = FakeElement()
    page = FakePage(
        selectors={
            "button#apply-button, a#apply-button, button.apply-button": apply_btn,
            "div.screening-question, div.assessment-question": [],
            "button[type='submit'], button.submit-btn": submit_btn,
        },
        contents="",
    )
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="naukri", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await NaukriCrawler().apply(context, job, user_profile={})

    assert receipt.success is True


@pytest.mark.asyncio
async def test_apply_returns_failure_receipt_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("timeout"))
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="naukri", portal_job_id="1", title="t", company="c", location="l", job_url="https://x")

    receipt = await NaukriCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.failure_reason == "timeout"


@pytest.mark.asyncio
async def test_check_application_status_finds_matching_row():
    page = FakePage(
        contents=(
            "<div class='applied-job-row'>app-123"
            "<span class='status'>Shortlisted</span></div>"
        )
    )
    context = FakeContext(pages_to_return=[page])
    status = await NaukriCrawler().check_application_status(context, "app-123")
    assert status == "shortlisted"


@pytest.mark.asyncio
async def test_check_application_status_defaults_to_applied_when_no_match():
    page = FakePage(contents="<div class='applied-job-row'>other</div>")
    context = FakeContext(pages_to_return=[page])
    status = await NaukriCrawler().check_application_status(context, "app-123")
    assert status == "applied"


@pytest.mark.asyncio
async def test_check_application_status_returns_unknown_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("boom"))
    context = FakeContext(pages_to_return=[page])
    status = await NaukriCrawler().check_application_status(context, "app-123")
    assert status == "unknown"


@pytest.mark.asyncio
async def test_answer_screening_questions_fills_matched_field():
    inp = FakeElement()
    question = FakeElement(text="What is your notice period?", children={"input, select, textarea": inp})
    missing = await NaukriCrawler()._answer_screening_questions(
        page=None, questions=[question], user_profile={"notice": "30"}
    )
    assert missing == []
    assert inp.filled == "30"


@pytest.mark.asyncio
async def test_answer_screening_questions_reports_unanswerable():
    question = FakeElement(text="Do you have a car?")
    missing = await NaukriCrawler()._answer_screening_questions(
        page=None, questions=[question], user_profile={}
    )
    assert missing == ["Do you have a car?"]


@pytest.mark.asyncio
async def test_extract_application_id_finds_match():
    page = FakePage(contents='{"application_id": "ABC-123"}')
    app_id = await NaukriCrawler()._extract_application_id(page)
    assert app_id == "ABC-123"


@pytest.mark.asyncio
async def test_extract_application_id_returns_none_on_exception():
    page = FakePage(raise_on_goto=None)

    class _BoomContent(FakePage):
        async def content(self):
            raise RuntimeError("dom gone")

    boom_page = _BoomContent()
    app_id = await NaukriCrawler()._extract_application_id(boom_page)
    assert app_id is None
