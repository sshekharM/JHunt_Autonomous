"""
Characterization tests for app.notifications.telegram_bot.

No real Telegram API calls -- telegram.Bot is monkeypatched with a fake.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.notifications import telegram_bot


@pytest.fixture(autouse=True)
def _reset_bot_singleton():
    telegram_bot._bot = None
    yield
    telegram_bot._bot = None


class _FakeBot:
    def __init__(self, token: str):
        self.token = token
        self.send_message = AsyncMock()


@pytest.mark.asyncio
async def test_send_message_returns_false_when_no_token_configured():
    with patch("app.notifications.telegram_bot.settings") as mock_settings:
        mock_settings.telegram_bot_token = ""
        result = await telegram_bot.send_message("chat-1", "hello")

    assert result is False


@pytest.mark.asyncio
async def test_send_message_returns_true_and_sends_via_bot_on_success():
    fake_bot = _FakeBot("token-123")
    with patch("app.notifications.telegram_bot.settings") as mock_settings, patch(
        "telegram.Bot", return_value=fake_bot
    ):
        mock_settings.telegram_bot_token = "token-123"
        result = await telegram_bot.send_message("chat-1", "hello")

    assert result is True
    fake_bot.send_message.assert_awaited_once_with(
        chat_id="chat-1", text="hello", parse_mode="HTML"
    )


@pytest.mark.asyncio
async def test_send_message_returns_false_and_logs_when_send_fails():
    fake_bot = _FakeBot("token-123")
    fake_bot.send_message.side_effect = RuntimeError("network down")

    with patch("app.notifications.telegram_bot.settings") as mock_settings, patch(
        "telegram.Bot", return_value=fake_bot
    ), patch("app.notifications.telegram_bot.logger") as mock_logger:
        mock_settings.telegram_bot_token = "token-123"
        result = await telegram_bot.send_message("chat-1", "hello")

    assert result is False
    mock_logger.error.assert_called_once()


def test_get_bot_caches_singleton_across_calls():
    with patch("telegram.Bot", return_value=_FakeBot("token-123")) as mock_bot_cls:
        with patch("app.notifications.telegram_bot.settings") as mock_settings:
            mock_settings.telegram_bot_token = "token-123"
            first = telegram_bot.get_bot()
            second = telegram_bot.get_bot()

    assert first is second
    mock_bot_cls.assert_called_once_with(token="token-123")


def test_get_bot_link_formats_start_url():
    with patch("app.notifications.telegram_bot.settings") as mock_settings:
        mock_settings.telegram_bot_username = "jhuntbot"
        link = telegram_bot.get_bot_link("user-42")

    assert link == "https://t.me/jhuntbot?start=user-42"
