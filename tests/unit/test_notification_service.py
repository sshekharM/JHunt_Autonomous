"""
Unit tests for notification_service.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenant_models.notification import NotificationChannel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email="user@example.com"):
    u = MagicMock()
    u.id = "user-001"
    u.email_encrypted = b"enc"
    return u


def _make_prefs(platform="telegram", telegram_chat_id="12345", discord_channel_id=None):
    p = MagicMock()
    p.notification_platform = MagicMock()
    p.notification_platform.value = platform
    p.telegram_chat_id = telegram_chat_id
    p.discord_channel_id = discord_channel_id
    return p


def _make_shared_db(user):
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute = AsyncMock(return_value=result)
    return db


def _make_tenant_db(prefs):
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = prefs
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_user_gets_three_channels():
    """Telegram user: in_app + email + telegram (3 channels)."""
    from app.tenant_models.profile import NotificationPlatform

    user = _make_user()
    prefs = _make_prefs(platform="telegram", telegram_chat_id="99")
    prefs.notification_platform = NotificationPlatform.telegram
    shared_db = _make_shared_db(user)
    tenant_db = _make_tenant_db(prefs)

    with patch("app.services.notification_service.decrypt", return_value="user@example.com"), \
         patch("app.services.notification_service.push_to_user", new=AsyncMock()) as mock_push, \
         patch("app.services.notification_service.email_client.send_email", new=AsyncMock(return_value=True)) as mock_email, \
         patch("app.services.notification_service.telegram_bot.send_message", new=AsyncMock(return_value=True)) as mock_tg, \
         patch("app.services.notification_service.discord_bot.send_to_channel", new=AsyncMock()) as mock_discord:

        from app.services.notification_service import notify
        await notify(
            user_id="user-001",
            event_type="job_applied",
            subject="Applied to X",
            body="body text",
            tenant_db=tenant_db,
            shared_db=shared_db,
        )

        mock_push.assert_called_once()
        mock_email.assert_called_once()
        mock_tg.assert_called_once_with(chat_id="99", text=mock_tg.call_args[1]["text"])
        mock_discord.assert_not_called()

    # Three NotificationLog rows should have been added
    assert tenant_db.add.call_count == 3


@pytest.mark.asyncio
async def test_discord_user_gets_three_channels():
    """Discord user: in_app + email + discord (3 channels)."""
    from app.tenant_models.profile import NotificationPlatform

    user = _make_user()
    prefs = _make_prefs(platform="discord", telegram_chat_id=None, discord_channel_id="555")
    prefs.notification_platform = NotificationPlatform.discord
    shared_db = _make_shared_db(user)
    tenant_db = _make_tenant_db(prefs)

    with patch("app.services.notification_service.decrypt", return_value="user@example.com"), \
         patch("app.services.notification_service.push_to_user", new=AsyncMock()), \
         patch("app.services.notification_service.email_client.send_email", new=AsyncMock(return_value=True)) as mock_email, \
         patch("app.services.notification_service.telegram_bot.send_message", new=AsyncMock()) as mock_tg, \
         patch("app.services.notification_service.discord_bot.send_to_channel", new=AsyncMock(return_value=True)) as mock_discord:

        from app.services.notification_service import notify
        await notify(
            user_id="user-001",
            event_type="job_applied",
            subject="Applied to Y",
            body="body",
            tenant_db=tenant_db,
            shared_db=shared_db,
        )

        mock_email.assert_called_once()
        mock_tg.assert_not_called()
        mock_discord.assert_called_once_with(channel_id="555", text=mock_discord.call_args[1]["text"])

    assert tenant_db.add.call_count == 3


@pytest.mark.asyncio
async def test_new_match_event_only_inapp():
    """new_match event skips email and platform delivery."""
    from app.tenant_models.profile import NotificationPlatform

    user = _make_user()
    prefs = _make_prefs(platform="telegram", telegram_chat_id="99")
    prefs.notification_platform = NotificationPlatform.telegram
    shared_db = _make_shared_db(user)
    tenant_db = _make_tenant_db(prefs)

    with patch("app.services.notification_service.decrypt", return_value="user@example.com"), \
         patch("app.services.notification_service.push_to_user", new=AsyncMock()) as mock_push, \
         patch("app.services.notification_service.email_client.send_email", new=AsyncMock()) as mock_email, \
         patch("app.services.notification_service.telegram_bot.send_message", new=AsyncMock()) as mock_tg, \
         patch("app.services.notification_service.discord_bot.send_to_channel", new=AsyncMock()) as mock_discord:

        from app.services.notification_service import notify
        await notify(
            user_id="user-001",
            event_type="new_match",
            subject="New job match",
            body="body",
            tenant_db=tenant_db,
            shared_db=shared_db,
        )

        mock_push.assert_called_once()
        mock_email.assert_not_called()
        mock_tg.assert_not_called()
        mock_discord.assert_not_called()

    # Only one NotificationLog row (in_app)
    assert tenant_db.add.call_count == 1


@pytest.mark.asyncio
async def test_channel_failure_does_not_propagate():
    """A failing channel must not raise; other channels still execute."""
    from app.tenant_models.profile import NotificationPlatform

    user = _make_user()
    prefs = _make_prefs(platform="telegram", telegram_chat_id="99")
    prefs.notification_platform = NotificationPlatform.telegram
    shared_db = _make_shared_db(user)
    tenant_db = _make_tenant_db(prefs)

    with patch("app.services.notification_service.decrypt", return_value="user@example.com"), \
         patch("app.services.notification_service.push_to_user", new=AsyncMock()), \
         patch("app.services.notification_service.email_client.send_email", new=AsyncMock(side_effect=RuntimeError("smtp down"))), \
         patch("app.services.notification_service.telegram_bot.send_message", new=AsyncMock(return_value=True)), \
         patch("app.services.notification_service.discord_bot.send_to_channel", new=AsyncMock()):

        from app.services.notification_service import notify
        # Must not raise
        await notify(
            user_id="user-001",
            event_type="job_applied",
            subject="Applied",
            body="body",
            tenant_db=tenant_db,
            shared_db=shared_db,
        )


@pytest.mark.asyncio
async def test_notification_log_rows_created_per_channel():
    """Each successful channel call creates a NotificationLog row."""
    from app.tenant_models.profile import NotificationPlatform

    user = _make_user()
    prefs = _make_prefs(platform="telegram", telegram_chat_id="42")
    prefs.notification_platform = NotificationPlatform.telegram
    shared_db = _make_shared_db(user)
    tenant_db = _make_tenant_db(prefs)

    with patch("app.services.notification_service.decrypt", return_value="user@example.com"), \
         patch("app.services.notification_service.push_to_user", new=AsyncMock()), \
         patch("app.services.notification_service.email_client.send_email", new=AsyncMock(return_value=True)), \
         patch("app.services.notification_service.telegram_bot.send_message", new=AsyncMock(return_value=True)), \
         patch("app.services.notification_service.discord_bot.send_to_channel", new=AsyncMock()):

        from app.services.notification_service import notify
        await notify(
            user_id="user-001",
            event_type="job_applied",
            subject="Applied",
            body="body",
            tenant_db=tenant_db,
            shared_db=shared_db,
        )

    # in_app + email + telegram = 3 rows
    assert tenant_db.add.call_count == 3
    logged_channels = [
        call_args[0][0].channel for call_args in tenant_db.add.call_args_list
    ]
    assert NotificationChannel.in_app in logged_channels
    assert NotificationChannel.email in logged_channels
    assert NotificationChannel.telegram in logged_channels
