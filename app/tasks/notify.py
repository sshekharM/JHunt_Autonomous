"""
Celery tasks for user notifications: high-match alerts and daily activity digests.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select

from app.database import AsyncSessionLocal, get_tenant_db, tenant_session
from app.tasks.celery_app import celery_app
from app.tenant_models.notification import NotificationChannel, NotificationLog

logger = structlog.get_logger("tasks.notify")


@celery_app.task
def send_match_notification(user_id: str, schema_name: str, jobs: list[dict]):
    """Tell the user about jobs that cleared the high-match threshold."""
    asyncio.run(_async_match_notification(user_id, schema_name, jobs))


async def _async_match_notification(user_id: str, schema_name: str, jobs: list[dict]) -> None:
    from app.services import notification_service

    count = len(jobs)
    items_html = "".join(
        f"<li><strong>{j['title']}</strong> at {j['company']} ({round(j['score'] * 100)}%)</li>"
        for j in jobs
    )
    async with AsyncSessionLocal() as shared_db, tenant_session(schema_name) as tenant_db:
        await notification_service.notify(
            user_id=user_id,
            event_type="new_match",
            subject=f"{count} new high-match job{'s' if count != 1 else ''}",
            body=f"<p>New jobs that closely match your profile:</p><ul>{items_html}</ul>",
            tenant_db=tenant_db,
            shared_db=shared_db,
        )
    logger.info("notify.match_sent", user_id=user_id, job_count=count)


@celery_app.task
def dispatch_activity_digest(user_id: str, schema_name: str):
    """Send a 24-hour activity digest to the user via notification_service."""
    asyncio.run(_async_digest(user_id, schema_name))


async def _async_digest(user_id: str, schema_name: str) -> None:
    from app.services import notification_service

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    async with AsyncSessionLocal() as shared_db:
        async for tenant_db in get_tenant_db(schema_name):
            # Count in-app notifications in last 24 hours
            count_result = await tenant_db.execute(
                select(func.count()).where(
                    NotificationLog.sent_at >= cutoff,
                    NotificationLog.channel == NotificationChannel.in_app,
                )
            )
            count = count_result.scalar_one()

            if count == 0:
                logger.info("notify.digest_empty", user_id=user_id)
                return

            # Fetch the events to include in the digest
            rows_result = await tenant_db.execute(
                select(NotificationLog).where(
                    NotificationLog.sent_at >= cutoff,
                    NotificationLog.channel == NotificationChannel.in_app,
                ).order_by(NotificationLog.sent_at.desc())
            )
            rows = rows_result.scalars().all()

            items_html = "".join(
                f"<li><strong>{r.event_type}</strong>: {r.subject or ''}</li>"
                for r in rows
            )
            body = (
                f"<p>Here is a summary of your jH_ANS activity over the past 24 hours "
                f"({count} event{'s' if count != 1 else ''}):</p>"
                f"<ul>{items_html}</ul>"
            )

            await notification_service.notify(
                user_id=user_id,
                event_type="digest",
                subject="Your daily jH_ANS activity summary",
                body=body,
                tenant_db=tenant_db,
                shared_db=shared_db,
            )
            logger.info("notify.digest_sent", user_id=user_id, event_count=count)
