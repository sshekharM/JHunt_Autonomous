import asyncio
import threading

import structlog

from app.config import settings

logger = structlog.get_logger("notifications.discord")

_loop: asyncio.AbstractEventLoop | None = None
_client = None  # discord.Client once started


def _run_bot():
    global _loop, _client
    import discord  # discord.py
    _loop = asyncio.new_event_loop()
    _client = discord.Client(intents=discord.Intents.default())
    try:
        _loop.run_until_complete(_client.start(settings.discord_bot_token))
    except Exception as exc:
        logger.error("discord.bot_crash", error=str(exc))


def start_discord_bot():
    if settings.discord_bot_token:
        t = threading.Thread(target=_run_bot, daemon=True)
        t.start()


async def send_to_channel(channel_id: str, text: str) -> bool:
    if _client is None or _loop is None:
        logger.warning("discord.not_started")
        return False
    try:
        channel = _client.get_channel(int(channel_id))
        if channel is None:
            logger.warning("discord.channel_not_found", channel_id=channel_id)
            return False
        future = asyncio.run_coroutine_threadsafe(channel.send(text), _loop)
        future.result(timeout=10)
        logger.info("discord.sent", channel_id=channel_id)
        return True
    except Exception as exc:
        logger.error("discord.send_failed", channel_id=channel_id, error=str(exc))
        return False


async def provision_user_channel(user_display_name: str) -> str | None:
    if _client is None or _loop is None:
        return None
    try:
        guild = _client.get_guild(int(settings.discord_guild_id))
        if guild is None:
            logger.warning("discord.guild_not_found", guild_id=settings.discord_guild_id)
            return None

        channel_name = f"user-{user_display_name.lower().replace(' ', '-')[:20]}"

        import discord
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        async def _create():
            ch = await guild.create_text_channel(name=channel_name, overwrites=overwrites)
            return str(ch.id)

        future = asyncio.run_coroutine_threadsafe(_create(), _loop)
        channel_id = future.result(timeout=15)
        logger.info("discord.channel_provisioned", name=channel_name, id=channel_id)
        return channel_id
    except Exception as exc:
        logger.error("discord.provision_failed", user=user_display_name, error=str(exc))
        return None
