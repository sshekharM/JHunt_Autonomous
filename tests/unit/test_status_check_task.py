"""
Characterization tests for app.tasks.status_check.
No real DB, Celery broker, or crawler network calls — everything below the
task boundary is faked. `.run()` on a bound Celery task already carries a
real (unbound-from-broker) task instance as `self`, so `self.retry(...)`
executes for real and we assert on what it actually raises today.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tenant_models.application import ApplicationStatus
from app.tenant_models.ml_feedback import OutcomeSignal

# ---------------------------------------------------------------------------
# check_all_application_statuses
# ---------------------------------------------------------------------------

def _users_factory(users):
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = users
    session.execute = AsyncMock(return_value=result)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


def test_dispatches_check_task_per_user():
    from app.tasks.status_check import (
        check_all_application_statuses,
        check_user_application_statuses,
    )

    user = MagicMock(id="u1", schema_name="u_abc")
    factory = _users_factory([user])

    with patch("app.tasks.status_check.AsyncSessionLocal", factory), patch.object(
        check_user_application_statuses, "delay"
    ) as mock_delay:
        check_all_application_statuses.run()

    mock_delay.assert_called_once_with("u1", "u_abc")


def test_dispatch_query_filters_active_onboarded_users():
    """Pin the WHERE clause itself (not just the mocked result) so a mutant
    flipping is_active/onboarding_complete to != or False is caught."""
    from app.tasks.status_check import (
        check_all_application_statuses,
        check_user_application_statuses,
    )

    factory = _users_factory([])
    with patch("app.tasks.status_check.AsyncSessionLocal", factory), patch.object(
        check_user_application_statuses, "delay"
    ):
        check_all_application_statuses.run()

    session = factory.return_value.__aenter__.return_value
    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "users.is_active = true" in compiled
    assert "users.onboarding_complete = true" in compiled


def test_dispatch_error_surfaces_from_retry():
    from app.tasks.status_check import check_all_application_statuses

    with patch(
        "app.tasks.status_check.AsyncSessionLocal", side_effect=RuntimeError("db down")
    ), pytest.raises(RuntimeError):
        check_all_application_statuses.run()


# ---------------------------------------------------------------------------
# check_user_application_statuses — shared fixtures
# ---------------------------------------------------------------------------

def _make_app(status, portal="linkedin", portal_application_id="pa-1", app_id="app-1"):
    app = MagicMock()
    app.id = app_id
    app.portal = portal
    app.portal_application_id = portal_application_id
    app.status = status
    app.job_title = "Backend Engineer"
    app.company = "Acme"
    app.match_score = 0.8
    return app


def _tenant_db_for(applications):
    tenant_db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = applications
    tenant_db.execute = AsyncMock(return_value=result)
    return tenant_db


def _fake_get_tenant_db(tenant_db):
    async def _gen(_schema_name):
        yield tenant_db
    return _gen


def _run_check_user(applications, **patches):
    """Runs check_user_application_statuses.run for one user with `applications`
    already "in the DB". `patches` overrides any of the default fakes below."""
    from app.tasks.status_check import check_user_application_statuses

    tenant_db = _tenant_db_for(applications)
    shared_factory = MagicMock()
    shared_factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    shared_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    ctx = {
        "app.tasks.status_check.AsyncSessionLocal": shared_factory,
        "app.tasks.status_check.get_tenant_db": _fake_get_tenant_db(tenant_db),
        "app.services.application_service._crawler_for_portal": MagicMock(),
        "app.crawlers.session_manager.get_context": AsyncMock(),
        "app.services.application_service.transition_status": AsyncMock(),
        "app.ml.feedback.record_outcome": AsyncMock(),
        "app.services.notification_service.notify": AsyncMock(),
    }
    ctx.update(patches)

    patchers = [patch(target, value) for target, value in ctx.items()]
    for p in patchers:
        p.start()
    try:
        check_user_application_statuses.run("user-1", "u_abc")
    finally:
        for p in patchers:
            p.stop()
    return tenant_db, ctx


def test_no_applications_skips_crawler_entirely():
    tenant_db, ctx = _run_check_user([])
    ctx["app.crawlers.session_manager.get_context"].assert_not_called()


def test_crawler_resolution_failure_skips_portal():
    app = _make_app(ApplicationStatus.applied)
    crawler_lookup = MagicMock(side_effect=RuntimeError("no crawler"))
    _, ctx = _run_check_user(
        [app], **{"app.services.application_service._crawler_for_portal": crawler_lookup}
    )
    ctx["app.services.application_service.transition_status"].assert_not_called()


def test_missing_portal_application_id_is_skipped():
    app = _make_app(ApplicationStatus.applied, portal_application_id=None)
    crawler = MagicMock()
    crawler.check_application_status = AsyncMock()
    _, ctx = _run_check_user(
        [app], **{"app.services.application_service._crawler_for_portal": MagicMock(return_value=crawler)}
    )
    crawler.check_application_status.assert_not_called()


def _run_with_raw_status(raw_status, app_status=ApplicationStatus.applied):
    app = _make_app(app_status)
    crawler = MagicMock()
    crawler.check_application_status = AsyncMock(return_value=raw_status)
    tenant_db, ctx = _run_check_user(
        [app], **{"app.services.application_service._crawler_for_portal": MagicMock(return_value=crawler)}
    )
    return app, ctx


def test_unmapped_portal_status_does_not_transition():
    _, ctx = _run_with_raw_status("some_unknown_status")
    ctx["app.services.application_service.transition_status"].assert_not_called()


def test_unchanged_status_does_not_transition():
    _, ctx = _run_with_raw_status("viewed", app_status=ApplicationStatus.viewed)
    ctx["app.services.application_service.transition_status"].assert_not_called()


def test_status_change_transitions_and_notifies():
    app, ctx = _run_with_raw_status("shortlisted", app_status=ApplicationStatus.applied)

    ctx["app.services.application_service.transition_status"].assert_awaited_once()
    kwargs = ctx["app.services.application_service.transition_status"].call_args.kwargs
    assert kwargs["application_id"] == app.id
    assert kwargs["new_status"] == ApplicationStatus.shortlisted
    assert kwargs["note"] == "portal reported: shortlisted"

    ctx["app.services.notification_service.notify"].assert_awaited_once()
    notify_kwargs = ctx["app.services.notification_service.notify"].call_args.kwargs
    assert notify_kwargs["user_id"] == "user-1"
    assert notify_kwargs["event_type"] == "status_changed"
    assert "shortlisted" in notify_kwargs["body"]


def test_meaningful_outcome_records_ml_feedback():
    app, ctx = _run_with_raw_status("interview", app_status=ApplicationStatus.shortlisted)

    ctx["app.ml.feedback.record_outcome"].assert_awaited_once()
    kwargs = ctx["app.ml.feedback.record_outcome"].call_args.kwargs
    assert kwargs["application_id"] == app.id
    assert kwargs["outcome"] == OutcomeSignal.interview_scheduled
    assert kwargs["user_id"] == "user-1"


def test_non_outcome_status_change_skips_ml_feedback():
    _, ctx = _run_with_raw_status("shortlisted", app_status=ApplicationStatus.applied)
    ctx["app.ml.feedback.record_outcome"].assert_not_awaited()


def test_record_outcome_failure_does_not_abort_notification():
    """The except around record_outcome must swallow the error, log it, and
    still let the status-change notification go out."""
    app = _make_app(ApplicationStatus.shortlisted)
    crawler = MagicMock()
    crawler.check_application_status = AsyncMock(return_value="interview")
    with patch("app.tasks.status_check.logger") as mock_logger:
        _, ctx = _run_check_user(
            [app],
            **{
                "app.services.application_service._crawler_for_portal": MagicMock(return_value=crawler),
                "app.ml.feedback.record_outcome": AsyncMock(side_effect=RuntimeError("feedback db down")),
            },
        )
    ctx["app.services.notification_service.notify"].assert_awaited_once()
    mock_logger.warning.assert_any_call(
        "status_check.feedback_error", application_id=app.id, error="feedback db down"
    )


def test_crawler_error_containing_404_marks_withdrawn():
    app = _make_app(ApplicationStatus.applied)
    crawler = MagicMock()
    crawler.check_application_status = AsyncMock(side_effect=RuntimeError("404 not found"))
    _, ctx = _run_check_user(
        [app], **{"app.services.application_service._crawler_for_portal": MagicMock(return_value=crawler)}
    )
    ctx["app.services.application_service.transition_status"].assert_awaited_once()
    kwargs = ctx["app.services.application_service.transition_status"].call_args.kwargs
    assert kwargs["new_status"] == ApplicationStatus.withdrawn
    assert kwargs["note"] == "portal returned 404 — assumed withdrawn"


def test_crawler_error_without_404_does_not_transition():
    app = _make_app(ApplicationStatus.applied)
    crawler = MagicMock()
    crawler.check_application_status = AsyncMock(side_effect=RuntimeError("timeout"))
    _, ctx = _run_check_user(
        [app], **{"app.services.application_service._crawler_for_portal": MagicMock(return_value=crawler)}
    )
    ctx["app.services.application_service.transition_status"].assert_not_called()


def test_withdrawal_transition_failure_after_404_is_swallowed_and_logged():
    """Second except: even if the withdrawal transition itself raises,
    check_user_application_statuses must not propagate the error, and must
    log it instead of silently dropping it."""
    app = _make_app(ApplicationStatus.applied)
    crawler = MagicMock()
    crawler.check_application_status = AsyncMock(side_effect=RuntimeError("404 gone"))
    # Should not raise despite transition_status failing.
    with patch("app.tasks.status_check.logger") as mock_logger:
        _run_check_user(
            [app],
            **{
                "app.services.application_service._crawler_for_portal": MagicMock(return_value=crawler),
                "app.services.application_service.transition_status": AsyncMock(
                    side_effect=RuntimeError("transition failed")
                ),
            },
        )
    mock_logger.warning.assert_any_call(
        "status_check.withdrawal_transition_error",
        application_id=app.id,
        error="transition failed",
    )


def test_per_user_check_error_surfaces_from_retry():
    from app.tasks.status_check import check_user_application_statuses

    with patch(
        "app.tasks.status_check.get_tenant_db", side_effect=RuntimeError("tenant db down")
    ), pytest.raises(RuntimeError):
        check_user_application_statuses.run("user-1", "u_abc")
