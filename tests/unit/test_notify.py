"""
Characterization tests for app.tasks.notify — the daily activity digest task.
No real DB or Celery broker: AsyncSessionLocal/get_tenant_db are faked.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _shared_db_factory():
    shared_db = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=shared_db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, shared_db


def _fake_get_tenant_db(tenant_db):
    async def _gen(_schema_name):
        yield tenant_db
    return _gen


def _tenant_db_with(count, rows):
    tenant_db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar_one.return_value = count
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = rows
    tenant_db.execute = AsyncMock(side_effect=[count_result, rows_result])
    return tenant_db


@pytest.mark.asyncio
async def test_digest_returns_early_when_no_events():
    from app.tasks.notify import _async_digest

    tenant_db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    tenant_db.execute = AsyncMock(return_value=count_result)
    factory, _ = _shared_db_factory()

    with patch("app.tasks.notify.AsyncSessionLocal", factory), patch(
        "app.tasks.notify.get_tenant_db", _fake_get_tenant_db(tenant_db)
    ), patch("app.services.notification_service.notify", new=AsyncMock()) as mock_notify:
        await _async_digest("user-1", "u_abc")

    mock_notify.assert_not_called()
    tenant_db.execute.assert_awaited_once()


def _make_row(event_type, subject):
    row = MagicMock()
    row.event_type = event_type
    row.subject = subject
    row.sent_at = datetime.now(timezone.utc)
    return row


async def _run_digest_with_events(rows, count=None):
    from app.tasks.notify import _async_digest

    tenant_db = _tenant_db_with(count if count is not None else len(rows), rows)
    factory, shared_db = _shared_db_factory()

    with patch("app.tasks.notify.AsyncSessionLocal", factory), patch(
        "app.tasks.notify.get_tenant_db", _fake_get_tenant_db(tenant_db)
    ), patch("app.services.notification_service.notify", new=AsyncMock()) as mock_notify:
        await _async_digest("user-1", "u_abc")

    return mock_notify, tenant_db, shared_db


@pytest.mark.asyncio
async def test_digest_calls_notify_with_in_app_summary():
    rows = [_make_row("job_applied", "Applied to X")]
    mock_notify, tenant_db, shared_db = await _run_digest_with_events(rows)

    mock_notify.assert_called_once()
    kwargs = mock_notify.call_args.kwargs
    assert kwargs["user_id"] == "user-1"
    assert kwargs["event_type"] == "digest"
    assert kwargs["subject"] == "Your daily jH_ANS activity summary"
    assert "<li><strong>job_applied</strong>: Applied to X</li>" in kwargs["body"]
    assert kwargs["tenant_db"] is tenant_db
    assert kwargs["shared_db"] is shared_db


@pytest.mark.asyncio
async def test_digest_singular_event_count_in_body():
    rows = [_make_row("job_applied", "Applied to X")]
    mock_notify, _, _ = await _run_digest_with_events(rows)
    assert "(1 event):" in mock_notify.call_args.kwargs["body"]


@pytest.mark.asyncio
async def test_digest_plural_event_count_in_body():
    rows = [_make_row("job_applied", "A"), _make_row("status_changed", "B")]
    mock_notify, _, _ = await _run_digest_with_events(rows)
    assert "2 events" in mock_notify.call_args.kwargs["body"]


@pytest.mark.asyncio
async def test_digest_defaults_missing_subject_to_empty_string():
    rows = [_make_row("job_applied", None)]
    mock_notify, _, _ = await _run_digest_with_events(rows)
    assert "<li><strong>job_applied</strong>: </li>" in mock_notify.call_args.kwargs["body"]


def test_dispatch_activity_digest_invokes_async_digest():
    from app.tasks.notify import dispatch_activity_digest

    with patch(
        "app.tasks.notify._async_digest", new=AsyncMock(return_value=None)
    ) as mock_digest:
        dispatch_activity_digest.run("user-1", "u_abc")

    mock_digest.assert_awaited_once_with("user-1", "u_abc")


@pytest.mark.asyncio
async def test_match_notification_sends_a_new_match_event():
    """Given high-scoring jobs, when the match notification runs, then the user
    gets one in-app 'new_match' notification listing each job and its score."""
    from app.tasks.notify import _async_match_notification

    tenant_db = AsyncMock()
    factory, shared_db = _shared_db_factory()
    jobs = [
        {"title": "Backend Engineer", "company": "Acme", "score": 0.912},
        {"title": "SRE", "company": "Globex", "score": 0.8},
    ]
    with patch("app.tasks.notify.AsyncSessionLocal", factory), patch(
        "app.tasks.notify.tenant_session", _fake_tenant_session(tenant_db)
    ), patch("app.services.notification_service.notify", new=AsyncMock()) as mock_notify:
        await _async_match_notification("user-1", "u_abc", jobs)

    kwargs = mock_notify.await_args.kwargs
    assert kwargs["user_id"] == "user-1" and kwargs["event_type"] == "new_match"
    assert kwargs["subject"] == "2 new high-match jobs"
    assert "<li><strong>Backend Engineer</strong> at Acme (91%)</li>" in kwargs["body"]
    assert "<li><strong>SRE</strong> at Globex (80%)</li>" in kwargs["body"]
    assert kwargs["tenant_db"] is tenant_db and kwargs["shared_db"] is shared_db


@pytest.mark.asyncio
async def test_match_notification_uses_singular_for_one_job():
    from app.tasks.notify import _async_match_notification

    factory, _ = _shared_db_factory()
    with patch("app.tasks.notify.AsyncSessionLocal", factory), patch(
        "app.tasks.notify.tenant_session", _fake_tenant_session(AsyncMock())
    ), patch("app.services.notification_service.notify", new=AsyncMock()) as mock_notify:
        await _async_match_notification("user-1", "u_abc", [{"title": "T", "company": "C", "score": 0.75}])

    assert mock_notify.await_args.kwargs["subject"] == "1 new high-match job"


def test_send_match_notification_runs_the_async_body():
    from app.tasks import notify

    with patch.object(notify, "_async_match_notification", new=AsyncMock()) as body:
        notify.send_match_notification("user-1", "u_abc", [])
    body.assert_awaited_once_with("user-1", "u_abc", [])


def _fake_tenant_session(tenant_db):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _cm(_schema_name):
        yield tenant_db
    return _cm
