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
