"""
Central notification fan-out service.
Pushes in-app + email + platform (telegram/discord) based on user preferences.
"""
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.notifications import email_client, telegram_bot, discord_bot
from app.routers.notifications import push_to_user
from app.security.encryption import decrypt
from app.tenant_models.notification import NotificationChannel, NotificationLog
from app.tenant_models.profile import NotificationPlatform, UserPreferences

logger = structlog.get_logger("services.notification")

# These event types skip email and platform delivery — in-app only
_IN_APP_ONLY_EVENTS = {"new_match"}


async def notify(
    user_id: str,
    event_type: str,
    subject: str,
    body: str,
    tenant_db: AsyncSession,
    shared_db: AsyncSession,
    deep_link: str | None = None,
) -> None:
    # Retrieve email from shared DB
    user_email: str | None = None
    try:
        result = await shared_db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.email_encrypted:
            user_email = decrypt(user.email_encrypted)
    except Exception as exc:
        logger.warning("notify.email_fetch_failed", user_id=user_id, error=str(exc))

    # Retrieve preferences from tenant DB
    prefs: UserPreferences | None = None
    try:
        pref_result = await tenant_db.execute(select(UserPreferences))
        prefs = pref_result.scalar_one_or_none()
    except Exception as exc:
        logger.warning("notify.prefs_fetch_failed", user_id=user_id, error=str(exc))

    send_non_inapp = event_type not in _IN_APP_ONLY_EVENTS

    # 1. In-app push (always)
    try:
        await push_to_user(user_id, {"event": event_type, "subject": subject, "body": body})
        await _log_notification(
            tenant_db=tenant_db,
            event_type=event_type,
            channel=NotificationChannel.in_app,
            subject=subject,
            body=body,
            delivered=True,
        )
    except Exception as exc:
        logger.error("notify.inapp_failed", user_id=user_id, error=str(exc))

    if not send_non_inapp:
        return

    # 2. Email (always for non-in_app_only events)
    if user_email:
        try:
            html_body = _build_html(subject, body, deep_link)
            ok = await email_client.send_email(to=user_email, subject=subject, body_html=html_body)
            await _log_notification(
                tenant_db=tenant_db,
                event_type=event_type,
                channel=NotificationChannel.email,
                subject=subject,
                body=body,
                delivered=ok,
            )
        except Exception as exc:
            logger.error("notify.email_failed", user_id=user_id, error=str(exc))

    if prefs is None:
        return

    # 3. Telegram
    if (
        prefs.notification_platform == NotificationPlatform.telegram
        and prefs.telegram_chat_id
    ):
        try:
            msg = _build_plain(subject, body, deep_link)
            ok = await telegram_bot.send_message(chat_id=prefs.telegram_chat_id, text=msg)
            await _log_notification(
                tenant_db=tenant_db,
                event_type=event_type,
                channel=NotificationChannel.telegram,
                subject=subject,
                body=body,
                delivered=ok,
            )
        except Exception as exc:
            logger.error("notify.telegram_failed", user_id=user_id, error=str(exc))

    # 4. Discord
    if (
        prefs.notification_platform == NotificationPlatform.discord
        and prefs.discord_channel_id
    ):
        try:
            msg = _build_plain(subject, body, deep_link)
            ok = await discord_bot.send_to_channel(channel_id=prefs.discord_channel_id, text=msg)
            await _log_notification(
                tenant_db=tenant_db,
                event_type=event_type,
                channel=NotificationChannel.discord,
                subject=subject,
                body=body,
                delivered=ok,
            )
        except Exception as exc:
            logger.error("notify.discord_failed", user_id=user_id, error=str(exc))


async def _log_notification(
    tenant_db: AsyncSession,
    event_type: str,
    channel: NotificationChannel,
    subject: str,
    body: str,
    delivered: bool,
) -> None:
    row = NotificationLog(
        id=str(uuid.uuid4()),
        event_type=event_type,
        channel=channel,
        subject=subject,
        body_snippet=body[:500] if body else None,
        delivered=delivered,
        sent_at=datetime.now(timezone.utc),
    )
    tenant_db.add(row)
    await tenant_db.commit()


def _build_html(subject: str, body: str, deep_link: str | None) -> str:
    link_html = ""
    if deep_link:
        link_html = f'<p><a href="{deep_link}">View in jH_ANS →</a></p>'
    return f"<h2>{subject}</h2><p>{body}</p>{link_html}"


def _build_plain(subject: str, body: str, deep_link: str | None) -> str:
    text = f"<b>{subject}</b>\n{body}"
    if deep_link:
        text += f"\n<a href='{deep_link}'>View in jH_ANS</a>"
    return text
