"""
Characterization tests for app/notifications/discord_bot.py.
_client/_loop are module-level singletons populated by the background
bot thread; tests monkeypatch them directly and fake
asyncio.run_coroutine_threadsafe so nothing touches a real event loop
running on another thread.
"""
import asyncio
import concurrent.futures
from types import SimpleNamespace
from unittest.mock import MagicMock

import discord
import pytest

from app.notifications import discord_bot


def _fake_run_coroutine_threadsafe(coro, loop):
    """Runs the coroutine to completion on a real worker thread with its own
    throwaway loop -- stands in for the real cross-thread scheduling
    send_to_channel/provision_user_channel rely on (a same-thread nested
    run_until_complete would raise "event loop already running")."""
    def runner():
        worker_loop = asyncio.new_event_loop()
        try:
            return worker_loop.run_until_complete(coro)
        finally:
            worker_loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        value = pool.submit(runner).result()
    return SimpleNamespace(result=lambda timeout=None: value)


@pytest.fixture(autouse=True)
def _reset_module_state():
    discord_bot._client = None
    discord_bot._loop = None
    yield
    discord_bot._client = None
    discord_bot._loop = None


def test_start_discord_bot_starts_a_daemon_thread_when_token_configured(monkeypatch):
    started = MagicMock()
    received_kwargs = {}

    def fake_thread(**kwargs):
        received_kwargs.update(kwargs)
        return started

    monkeypatch.setattr(discord_bot.settings, "discord_bot_token", "a-token")
    monkeypatch.setattr(discord_bot.threading, "Thread", fake_thread)

    discord_bot.start_discord_bot()

    started.start.assert_called_once()
    assert received_kwargs["daemon"] is True


def test_start_discord_bot_does_nothing_without_a_token(monkeypatch):
    thread_class = MagicMock()
    monkeypatch.setattr(discord_bot.settings, "discord_bot_token", "")
    monkeypatch.setattr(discord_bot.threading, "Thread", thread_class)

    discord_bot.start_discord_bot()

    thread_class.assert_not_called()


@pytest.mark.parametrize(
    "client, loop",
    [(None, None), (MagicMock(), None), (None, MagicMock())],
    ids=["both_unset", "only_client_set", "only_loop_set"],
)
def test_send_to_channel_returns_false_when_bot_not_fully_started(client, loop):
    """Pins `_client is None or _loop is None`: both must be set, not just
    one -- an `and` here would wrongly proceed with only one populated."""
    discord_bot._client = client
    discord_bot._loop = loop

    ok = asyncio.run(discord_bot.send_to_channel("123", "hello"))

    assert ok is False


def test_send_to_channel_never_touches_the_client_when_loop_is_unset():
    """Stronger pin for the `or`: with _loop unset, _client.get_channel must
    never be reached -- an `and` mutation would call it and the return value
    alone (also False, via a downstream failure) would not catch that."""
    client = MagicMock()
    discord_bot._client = client
    discord_bot._loop = None

    asyncio.run(discord_bot.send_to_channel("123", "hello"))

    client.get_channel.assert_not_called()


@pytest.mark.parametrize(
    "client, loop",
    [(None, None), (MagicMock(), None), (None, MagicMock())],
    ids=["both_unset", "only_client_set", "only_loop_set"],
)
def test_provision_user_channel_returns_none_when_bot_not_fully_started(client, loop):
    discord_bot._client = client
    discord_bot._loop = loop

    channel_id = asyncio.run(discord_bot.provision_user_channel("Jane Doe"))

    assert channel_id is None


def test_provision_user_channel_never_touches_the_client_when_loop_is_unset(monkeypatch):
    client = MagicMock()
    discord_bot._client = client
    discord_bot._loop = None
    monkeypatch.setattr(discord_bot.settings, "discord_guild_id", "1")

    asyncio.run(discord_bot.provision_user_channel("Jane Doe"))

    client.get_guild.assert_not_called()


def test_send_to_channel_returns_false_when_send_raises(monkeypatch):
    text_channel = MagicMock(spec=discord.TextChannel)

    async def raising_send(text):
        raise RuntimeError("discord api down")

    text_channel.send = raising_send
    client = MagicMock()
    client.get_channel.return_value = text_channel
    discord_bot._client = client
    discord_bot._loop = MagicMock()
    monkeypatch.setattr(discord_bot.asyncio, "run_coroutine_threadsafe", _fake_run_coroutine_threadsafe)

    ok = asyncio.run(discord_bot.send_to_channel("123", "hello"))

    assert ok is False




def test_send_to_channel_sends_when_channel_is_messageable(monkeypatch):
    text_channel = MagicMock(spec=discord.TextChannel)

    async def fake_send(text):
        text_channel.sent_text = text

    text_channel.send = fake_send
    client = MagicMock()
    client.get_channel.return_value = text_channel
    discord_bot._client = client
    discord_bot._loop = MagicMock()
    monkeypatch.setattr(discord_bot.asyncio, "run_coroutine_threadsafe", _fake_run_coroutine_threadsafe)

    ok = asyncio.run(discord_bot.send_to_channel("123", "hello"))

    assert ok is True
    assert text_channel.sent_text == "hello"


def test_send_to_channel_warns_and_returns_false_for_a_non_messageable_channel(monkeypatch):
    """A CategoryChannel has no .send -- must be rejected explicitly rather
    than relying on the generic except to swallow an AttributeError."""
    category_channel = MagicMock(spec=discord.CategoryChannel)
    client = MagicMock()
    client.get_channel.return_value = category_channel
    discord_bot._client = client
    discord_bot._loop = MagicMock()
    monkeypatch.setattr(discord_bot.asyncio, "run_coroutine_threadsafe", _fake_run_coroutine_threadsafe)

    with pytest.MonkeyPatch.context() as mp:
        mock_logger = MagicMock()
        mp.setattr(discord_bot, "logger", mock_logger)
        ok = asyncio.run(discord_bot.send_to_channel("123", "hello"))

    assert ok is False
    mock_logger.warning.assert_called_once_with(
        "discord.channel_not_found", channel_id="123"
    )
    mock_logger.error.assert_not_called()


def test_provision_user_channel_grants_only_the_bot_member_view_access(monkeypatch):
    everyone = MagicMock(spec=discord.Role)
    bot_member = MagicMock(spec=discord.Member)
    created_channel = MagicMock(spec=discord.TextChannel)
    created_channel.id = 999
    received: dict = {}

    async def fake_create_text_channel(name, overwrites):
        received["overwrites"] = overwrites
        return created_channel

    guild = MagicMock()
    guild.default_role = everyone
    guild.me = bot_member
    guild.create_text_channel = fake_create_text_channel

    client = MagicMock()
    client.get_guild.return_value = guild
    discord_bot._client = client
    discord_bot._loop = MagicMock()
    monkeypatch.setattr(discord_bot.asyncio, "run_coroutine_threadsafe", _fake_run_coroutine_threadsafe)
    monkeypatch.setattr(discord_bot.settings, "discord_guild_id", "1")

    channel_id = asyncio.run(discord_bot.provision_user_channel("Jane Doe"))

    assert channel_id == "999"
    overwrites = received["overwrites"]
    assert overwrites[everyone].view_channel is False
    assert overwrites[bot_member].view_channel is True
