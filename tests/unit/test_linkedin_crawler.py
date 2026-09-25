"""
Characterization tests for app/crawlers/linkedin.py.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.crawlers.base import RawJob
from app.crawlers.linkedin import LinkedInCrawler
from tests.unit.crawler_fakes import ClickNavPage, FakeContext, FakeElement, FakePage


@pytest.fixture(autouse=True)
def _patched_helpers():
    with patch("app.crawlers.linkedin.human_delay", new=AsyncMock()), \
            patch("app.crawlers.linkedin.micro_delay", new=AsyncMock()), \
            patch("app.crawlers.linkedin.random_scroll", new=AsyncMock()), \
            patch("app.crawlers.linkedin.human_type", new=AsyncMock()), \
            patch("app.crawlers.linkedin.save_session_cookies", new=AsyncMock()), \
            patch("app.crawlers.linkedin.audit") as audit_mock:
        yield audit_mock


def _job_card(title="Engineer", company="Acme", loc="Pune", href="/jobs/view/123", easy_apply=None):
    children = {
        "h3.base-search-card__title, a.job-card-list__title": FakeElement(text=title),
        "h4.base-search-card__subtitle, a.job-card-container__company-name": FakeElement(text=company),
        "span.job-search-card__location, li.job-card-container__metadata-item": FakeElement(text=loc),
        "a.base-card__full-link, a.job-card-list__title": FakeElement(attrs={"href": href}),
    }
    if easy_apply is not None:
        children["span.job-search-card__easy-apply-label"] = easy_apply
    return FakeElement(children=children)


@pytest.mark.asyncio
async def test_login_success_when_redirected_to_feed():
    page = ClickNavPage(url_after_click="https://www.linkedin.com/feed/")
    context = FakeContext(pages_to_return=[page])
    ok = await LinkedInCrawler().login(context)
    assert ok is True


@pytest.mark.asyncio
async def test_login_success_when_only_mynetwork_in_url():
    """Isolates each `or` in the feed/mynetwork/jobs check: only 'mynetwork'
    present still means success, whichever `or` a mutant flips to `and`."""
    page = ClickNavPage(url_after_click="https://www.linkedin.com/mynetwork/invitations")
    context = FakeContext(pages_to_return=[page])
    ok = await LinkedInCrawler().login(context)
    assert ok is True


@pytest.mark.asyncio
async def test_login_audits_challenge_on_checkpoint_only(_patched_helpers):
    """Isolates the checkpoint/challenge `or`: 'checkpoint' alone must still
    be treated as a challenge (not the generic login-failed branch, which
    also returns False), whichever side a mutant flips to `and`."""
    page = ClickNavPage(url_after_click="https://www.linkedin.com/checkpoint/verify")
    context = FakeContext(pages_to_return=[page])
    ok = await LinkedInCrawler().login(context)
    assert ok is False
    _patched_helpers.assert_called_once_with(
        "crawler.login_challenge", details={"portal": "linkedin", "url": page.url}
    )


@pytest.mark.asyncio
async def test_login_audits_challenge_on_challenge_only(_patched_helpers):
    page = ClickNavPage(url_after_click="https://www.linkedin.com/challenge/verify")
    context = FakeContext(pages_to_return=[page])
    ok = await LinkedInCrawler().login(context)
    assert ok is False
    _patched_helpers.assert_called_once_with(
        "crawler.login_challenge", details={"portal": "linkedin", "url": page.url}
    )


@pytest.mark.asyncio
async def test_login_returns_false_when_url_unrecognised():
    page = ClickNavPage(url_after_click="https://www.linkedin.com/uas/login-submit")
    context = FakeContext(pages_to_return=[page])
    ok = await LinkedInCrawler().login(context)
    assert ok is False


@pytest.mark.asyncio
async def test_login_logs_and_returns_false_when_close_fails_on_exception():
    class _BoomOnClose(FakePage):
        async def close(self):
            raise RuntimeError("already closed")

    page = _BoomOnClose(raise_on_goto=RuntimeError("net down"))
    context = FakeContext(pages_to_return=[page])

    with patch("app.crawlers.linkedin.logger") as mock_logger:
        ok = await LinkedInCrawler().login(context)

    assert ok is False
    mock_logger.warning.assert_called_once_with(
        "linkedin.page_close_failed", error="already closed"
    )


@pytest.mark.asyncio
async def test_search_jobs_parses_cards_and_marks_easy_apply():
    card = _job_card(easy_apply=FakeElement())
    page = FakePage(selectors={"div.job-search-card, li.jobs-search-results__list-item": [card]})
    context = FakeContext(pages_to_return=[page])

    jobs = await LinkedInCrawler().search_jobs(context, keywords=["python"], location="Pune", page_num=2)

    assert len(jobs) == 1
    assert jobs[0].portal_job_id == "123"
    assert jobs[0].is_easy_apply is True
    assert jobs[0].job_url == "https://www.linkedin.com/jobs/view/123"


@pytest.mark.asyncio
async def test_search_jobs_marks_not_easy_apply_when_badge_absent():
    card = _job_card()
    page = FakePage(selectors={"div.job-search-card, li.jobs-search-results__list-item": [card]})
    context = FakeContext(pages_to_return=[page])

    jobs = await LinkedInCrawler().search_jobs(context, keywords=["python"])

    assert jobs[0].is_easy_apply is False


@pytest.mark.asyncio
async def test_search_jobs_skips_card_parse_errors_and_continues():
    good = _job_card()
    bad = FakeElement(children={})  # no link element -> _parse_job_card returns None

    class _BoomCard(FakeElement):
        async def query_selector(self, sel):
            raise RuntimeError("dom crash")

    page = FakePage(
        selectors={
            "div.job-search-card, li.jobs-search-results__list-item": [bad, _BoomCard(), good],
        }
    )
    context = FakeContext(pages_to_return=[page])

    jobs = await LinkedInCrawler().search_jobs(context, keywords=["python"])

    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_search_jobs_returns_empty_list_on_navigation_error():
    page = FakePage(raise_on_goto=RuntimeError("boom"))
    context = FakeContext(pages_to_return=[page])

    jobs = await LinkedInCrawler().search_jobs(context, keywords=["python"])

    assert jobs == []
    assert page.closed is True


@pytest.mark.asyncio
async def test_parse_job_card_returns_none_when_link_missing():
    crawler = LinkedInCrawler()
    card = FakeElement(children={
        "h3.base-search-card__title, a.job-card-list__title": FakeElement(text="t"),
    })
    assert await crawler._parse_job_card(card, page=None) is None


@pytest.mark.asyncio
async def test_parse_job_card_returns_none_when_title_missing_without_side_effects():
    """Isolates the `not title_el or not link_el` guard: pins that a missing
    title_el short-circuits *before* querying the easy-apply badge, so a
    mutant flipping this `or` to `and` (which would fall through and only
    crash later on title_el.inner_text()) is caught by the missing query,
    not merely by both paths returning None."""

    class _TrackingCard(FakeElement):
        async def query_selector(self, sel):
            self.queried_selectors.append(sel)
            return await super().query_selector(sel)

    card = _TrackingCard(children={
        "a.base-card__full-link, a.job-card-list__title": FakeElement(attrs={"href": "/jobs/view/1"}),
    })
    card.queried_selectors = []

    result = await LinkedInCrawler()._parse_job_card(card, page=None)

    assert result is None
    assert "span.job-search-card__easy-apply-label" not in card.queried_selectors


@pytest.mark.asyncio
async def test_apply_flags_manual_when_not_easy_apply():
    job = RawJob(portal="linkedin", portal_job_id="1", title="t", company="c", location="l", job_url="https://x", is_easy_apply=False)
    receipt = await LinkedInCrawler().apply(context=None, job=job, user_profile={})
    assert receipt.success is False
    assert receipt.failure_reason == "not_easy_apply"
    assert receipt.requires_manual is True


@pytest.mark.asyncio
async def test_apply_flags_manual_when_easy_apply_button_missing():
    page = FakePage()
    context = FakeContext(pages_to_return=[page])
    job = RawJob(portal="linkedin", portal_job_id="1", title="t", company="c", location="l", job_url="https://x", is_easy_apply=True)

    receipt = await LinkedInCrawler().apply(context, job, user_profile={})

    assert receipt.success is False
    assert receipt.failure_reason == "easy_apply_button_not_found"


_TEXT_INPUTS_SEL = (
    "div.jobs-easy-apply-form-section__grouping input[type='text'],"
    "div.jobs-easy-apply-form-section__grouping textarea"
)
_SELECTS_SEL = "div.jobs-easy-apply-form-section__grouping select"
_NEXT_BTN_SEL = (
    "button[aria-label='Continue to next step'],"
    "button[aria-label='Submit application'],"
    "button[aria-label='Review your application']"
)


def _easy_apply_modal_selectors(text_inputs=None, next_btn=None):
    return {
        "button.jobs-apply-button, button[aria-label*='Easy Apply']": FakeElement(),
        "div.jobs-easy-apply-modal": FakeElement(),
        "input[type='file']": None,
        _TEXT_INPUTS_SEL: text_inputs or [],
        _SELECTS_SEL: [],
        _NEXT_BTN_SEL: next_btn,
    }


def _easy_apply_job():
    return RawJob(portal="linkedin", portal_job_id="1", title="t", company="c",
                  location="l", job_url="https://x", is_easy_apply=True)


@pytest.mark.asyncio
async def test_apply_submits_and_reports_missing_fields():
    unmapped_input = FakeElement(attrs={"aria-label": "Cover letter"})
    submit_btn = FakeElement(text="Submit application")
    selectors = _easy_apply_modal_selectors(text_inputs=[unmapped_input], next_btn=submit_btn)
    context = FakeContext(pages_to_return=[FakePage(selectors=selectors)])

    receipt = await LinkedInCrawler().apply(context, _easy_apply_job(), user_profile={"phone": "123"})

    assert receipt.success is True
    assert receipt.missing_fields == ["Cover letter"]


@pytest.mark.asyncio
async def test_apply_fills_matched_profile_field():
    phone_input = FakeElement(attrs={"aria-label": "Phone number"})
    submit_btn = FakeElement(text="Submit application")
    selectors = _easy_apply_modal_selectors(text_inputs=[phone_input], next_btn=submit_btn)
    context = FakeContext(pages_to_return=[FakePage(selectors=selectors)])

    receipt = await LinkedInCrawler().apply(context, _easy_apply_job(), user_profile={"phone": "9999999999"})

    assert receipt.success is True
    assert phone_input.filled == "9999999999"


@pytest.mark.asyncio
async def test_apply_returns_incomplete_when_no_next_button_found():
    selectors = _easy_apply_modal_selectors()
    context = FakeContext(pages_to_return=[FakePage(selectors=selectors)])

    receipt = await LinkedInCrawler().apply(context, _easy_apply_job(), user_profile={})

    assert receipt.success is False
    assert receipt.failure_reason == "modal_flow_incomplete"
    assert receipt.requires_manual is True


@pytest.mark.asyncio
async def test_apply_returns_failure_receipt_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("timeout"))
    context = FakeContext(pages_to_return=[page])

    receipt = await LinkedInCrawler().apply(context, _easy_apply_job(), user_profile={})

    assert receipt.success is False
    assert receipt.failure_reason == "timeout"


@pytest.mark.asyncio
async def test_check_application_status_returns_applied():
    page = FakePage()
    context = FakeContext(pages_to_return=[page])
    status = await LinkedInCrawler().check_application_status(context, portal_application_id="x")
    assert status == "applied"


@pytest.mark.asyncio
async def test_check_application_status_returns_unknown_on_exception():
    page = FakePage(raise_on_goto=RuntimeError("boom"))
    context = FakeContext(pages_to_return=[page])
    status = await LinkedInCrawler().check_application_status(context, portal_application_id="x")
    assert status == "unknown"


@pytest.mark.parametrize(
    "label,profile,expected",
    [
        ("Notice period (days)", {"notice_period_days": 30}, "30"),
        ("Mobile number", {"phone": "999"}, "999"),
        ("Years of experience", {"years_experience": 5}, "5"),
        ("Current city", {"city": "Pune"}, "Pune"),
        ("Current salary", {"current_salary": 10}, "10"),
        ("Expected salary", {"salary_min_lpa": 12}, "12"),
        ("Unmapped field", {}, None),
    ],
)
def test_match_profile_field(label, profile, expected):
    assert LinkedInCrawler()._match_profile_field(label, profile) == expected
