"""
Celery tasks for polling application statuses across portals.
"""
import asyncio
from app.services import notification_service

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal, get_tenant_db
from app.models.user import User
from app.tasks.celery_app import celery_app

logger = structlog.get_logger("tasks.status_check")

# Statuses that are still "live" and worth re-checking
_LIVE_STATUSES = {
    "applied",
    "viewed",
    "shortlisted",
    "interview_scheduled",
}

# Mapping from portal-returned strings to ApplicationStatus enum values
_PORTAL_STATUS_MAP = {
    "viewed": "viewed",
    "shortlisted": "shortlisted",
    "interview": "interview_scheduled",
    "interview_scheduled": "interview_scheduled",
    "rejected": "rejected",
    "withdrawn": "withdrawn",
    "expired": "withdrawn",
}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(bind=True, max_retries=3)
def check_all_application_statuses(self):
    """Dispatch per-user status check tasks for all active users."""
    async def _inner():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.is_active == True, User.onboarding_complete == True)
            )
            users = result.scalars().all()

        count = 0
        for user in users:
            check_user_application_statuses.delay(user.id, user.schema_name)
            count += 1
        logger.info("status_check.dispatched", user_count=count)

    try:
        _run(_inner())
    except Exception as exc:
        logger.error("status_check.dispatch_error", error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=2)
def check_user_application_statuses(self, user_id: str, schema_name: str):
    """
    Re-check all live applications for one user.
    Calls the appropriate portal crawler and updates the FSM status.
    """
    async def _inner():
        from app.tenant_models.application import JobApplication, ApplicationStatus
        from app.services.application_service import transition_status
        from app.crawlers.session_manager import get_context

        async for tenant_db in get_tenant_db(schema_name):
            result = await tenant_db.execute(
                select(JobApplication).where(
                    JobApplication.status.in_([
                        ApplicationStatus.applied,
                        ApplicationStatus.viewed,
                        ApplicationStatus.shortlisted,
                        ApplicationStatus.interview_scheduled,
                    ])
                )
            )
            applications = result.scalars().all()

            if not applications:
                return

            # Group by portal to reuse browser context
            from collections import defaultdict
            by_portal: dict[str, list] = defaultdict(list)
            for app in applications:
                by_portal[app.portal].append(app)

            for portal, apps in by_portal.items():
                try:
                    from app.services.application_service import _crawler_for_portal
                    crawler = _crawler_for_portal(portal)
                    context = await get_context(f"user_{user_id}_{portal}")
                except Exception as exc:
                    logger.warning(
                        "status_check.no_crawler",
                        portal=portal,
                        error=str(exc),
                    )
                    continue

                for app in apps:
                    if not app.portal_application_id:
                        continue
                    try:
                        raw_status = await crawler.check_application_status(
                            context, app.portal_application_id
                        )
                        new_status_str = _PORTAL_STATUS_MAP.get(raw_status.lower())
                        if new_status_str is None:
                            continue

                        new_status = ApplicationStatus(new_status_str)
                        if new_status == app.status:
                            continue

                        await transition_status(
                            application_id=app.id,
                            new_status=new_status,
                            tenant_db=tenant_db,
                            note=f"portal reported: {raw_status}",
                        )

                        # Update ML feedback for meaningful outcomes
                        from app.tenant_models.ml_feedback import OutcomeSignal
                        from app.ml.feedback import record_outcome
                        outcome_map = {
                            ApplicationStatus.interview_scheduled: OutcomeSignal.interview_scheduled,
                            ApplicationStatus.rejected: OutcomeSignal.rejected_by_recruiter,
                            ApplicationStatus.withdrawn: OutcomeSignal.withdrawn_by_user,
                        }
                        if new_status in outcome_map:
                            try:
                                await record_outcome(
                                    application_id=app.id,
                                    portal=portal,
                                    job_title=app.job_title,
                                    match_score=app.match_score,
                                    outcome=outcome_map[new_status],
                                    tenant_db=tenant_db,
                                    user_id=user_id,
                                )
                            except Exception:
                                pass

                        logger.info(
                            "status_check.updated",
                            user_id=user_id,
                            application_id=app.id,
                            old=app.status.value,
                            new=new_status_str,
                        )

                        async with AsyncSessionLocal() as shared_db:
                            await notification_service.notify(
                                user_id=user_id,
                                event_type="status_changed",
                                subject=f"Application update: {app.job_title} at {app.company}",
                                body=f"Your application status changed to {new_status_str}.",
                                tenant_db=tenant_db,
                                shared_db=shared_db,
                            )

                    except Exception as exc:
                        logger.warning(
                            "status_check.app_error",
                            application_id=app.id,
                            error=str(exc),
                        )
                        # Mark portal error if it looks like a 404/withdrawn
                        if "404" in str(exc) or "not found" in str(exc).lower():
                            try:
                                await transition_status(
                                    application_id=app.id,
                                    new_status=ApplicationStatus.withdrawn,
                                    tenant_db=tenant_db,
                                    note="portal returned 404 — assumed withdrawn",
                                )
                            except Exception:
                                pass

    try:
        _run(_inner())
    except Exception as exc:
        logger.error(
            "check_user_application_statuses.error",
            user_id=user_id,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=120)
