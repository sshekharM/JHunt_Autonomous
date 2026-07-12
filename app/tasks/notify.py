"""
Celery task for daily activity digests.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, func

from app.database import AsyncSessionLocal, get_tenant_db
from app.tasks.celery_app import celery_app
from app.tenant_models.notification import NotificationChannel, NotificationLog

logger = structlog.get_logger("tasks.notify")


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
