import structlog

from app.config import settings

logger = structlog.get_logger("notifications.telegram")

_bot = None


def get_bot():
    global _bot
    if _bot is None:
        from telegram import Bot  # python-telegram-bot v20+
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


async def send_message(chat_id: str, text: str) -> bool:
    if not settings.telegram_bot_token:
        return False
    try:
        from telegram.error import TelegramError
        await get_bot().send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        logger.info("telegram.sent", chat_id=chat_id)
        return True
    except Exception as exc:
        logger.error("telegram.send_failed", chat_id=chat_id, error=str(exc))
        return False


def get_bot_link(user_id: str) -> str:
    return f"https://t.me/{settings.telegram_bot_username}?start={user_id}"
