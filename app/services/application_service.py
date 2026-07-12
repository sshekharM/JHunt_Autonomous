"""
Core application orchestration: apply, FSM transitions, HITL queuing.
"""
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawlers.base import ApplicationReceipt, BaseCrawler
from app.crawlers.session_manager import get_context
from app.ml.feedback import record_outcome
from app.security.audit_log import audit
from app.tenant_models.application import (
    ApplicationFailureReason,
    ApplicationStatus,
    ApplicationStatusLog,
    JobApplication,
)
from app.tenant_models.ml_feedback import OutcomeSignal
from app.tenant_models.screening_qa import MissingInfoLog

logger = structlog.get_logger("services.application")

# ---------------------------------------------------------------------------
# FSM — only these transitions are permitted
# ---------------------------------------------------------------------------
_VALID_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.pending_hitl: {
        ApplicationStatus.applying,
        ApplicationStatus.withdrawn,
    },
    ApplicationStatus.applying: {
        ApplicationStatus.applied,
        ApplicationStatus.failed_portal_error,
    },
    ApplicationStatus.applied: {
        ApplicationStatus.viewed,
        ApplicationStatus.shortlisted,
        ApplicationStatus.rejected,
        ApplicationStatus.withdrawn,
    },
    ApplicationStatus.viewed: {
        ApplicationStatus.shortlisted,
        ApplicationStatus.rejected,
    },
    ApplicationStatus.shortlisted: {
        ApplicationStatus.interview_scheduled,
        ApplicationStatus.rejected,
    },
    ApplicationStatus.interview_scheduled: {
        ApplicationStatus.rejected,
    },
}

# offer_received is not in the current enum; when added it should extend the FSM here.


def _crawler_for_portal(portal: str) -> BaseCrawler:
    """Lazy import to avoid circular deps and heavy Playwright at import time."""
    from app.crawlers.naukri import NaukriCrawler
    from app.crawlers.linkedin import LinkedInCrawler
    from app.crawlers.glassdoor import GlassdoorCrawler
    from app.crawlers.indeed import IndeedCrawler

    mapping: dict[str, type[BaseCrawler]] = {
        "naukri": NaukriCrawler,
        "linkedin": LinkedInCrawler,
        "glassdoor": GlassdoorCrawler,
        "indeed": IndeedCrawler,
    }
    cls = mapping.get(portal.lower())
    if cls is None:
        raise ValueError(f"No crawler registered for portal: {portal!r}")
    return cls()


async def apply_to_job(
    user_id: str,
    job_id: str,
    schema_name: str,
    tenant_db: AsyncSession,
    shared_db: AsyncSession,
    resume_path: str,
    cover_letter: str,
    job_record: Optional[object] = None,
) -> ApplicationReceipt:
    """
    Full apply flow:
      1. Fetch job record (passed in or queried).
      2. Acquire portal browser context.
      3. Call crawler.apply().
      4. Persist JobApplication + status log.
      5. Log missing fields and ML feedback signal.
    """
    # Resolve job record if not provided
    if job_record is None:
        from app.tenant_models.job import MatchedJob
        result = await tenant_db.execute(
            select(MatchedJob).where(MatchedJob.id == job_id)
        )
        job_record = result.scalar_one()

    portal = job_record.portal

    # Build a minimal user_profile dict for the crawler
    user_profile = {"user_id": user_id, "resume_path": resume_path}

    # Obtain a RawJob-like dict the crawler can work with
    from app.crawlers.base import RawJob
    raw_job = RawJob(
        portal=portal,
        portal_job_id=job_record.portal_job_id,
        title=job_record.title,
        company=job_record.company,
        location=job_record.location,
        job_url=job_record.job_url,
    )

    crawler = _crawler_for_portal(portal)
    context = await get_context(f"user_{user_id}_{portal}")

    receipt: ApplicationReceipt = await crawler.apply(
        context=context,
        job=raw_job,
        user_profile=user_profile,
        resume_path=resume_path,
        cover_letter=cover_letter,
    )

    now = datetime.now(timezone.utc)
    status = ApplicationStatus.applied if receipt.success else ApplicationStatus.failed_portal_error
    failure_reason = (
        None if receipt.success
        else ApplicationFailureReason.unknown
    )
    if not receipt.success and receipt.failure_reason == "missing_info":
        failure_reason = ApplicationFailureReason.missing_profile_info
        status = ApplicationStatus.failed_missing_info

    app = JobApplication(
        matched_job_id=job_id,
        portal=portal,
        portal_job_id=raw_job.portal_job_id,
        portal_application_id=receipt.portal_application_id,
        job_title=raw_job.title,
        company=raw_job.company,
        match_score=getattr(job_record, "match_score", 0.0),
        status=status,
        failure_reason=failure_reason,
        failure_detail=receipt.failure_reason,
        applied_at=now if receipt.success else None,
    )
    tenant_db.add(app)
    await tenant_db.flush()  # get app.id before appending log

    log_entry = ApplicationStatusLog(
        application_id=app.id,
        from_status=None,
        to_status=status.value,
        note="initial apply" if receipt.success else receipt.failure_reason,
    )
    tenant_db.add(log_entry)

    # Log missing fields for HITL resolution
    for field_name in receipt.missing_fields:
        missing = MissingInfoLog(portal=portal, field_name=field_name, field_label=field_name)
        tenant_db.add(missing)

    await tenant_db.commit()
    audit(
        "application.submitted" if receipt.success else "application.failed",
        user_id=user_id,
        details={"job_id": job_id, "portal": portal, "application_id": app.id},
    )

    # Record ML feedback signal
    if receipt.success:
        from app.tenant_models.ml_feedback import OutcomeSignal
        # We record "no_response" initially; updated later via status_check
        try:
            await record_outcome(
                application_id=app.id,
                portal=portal,
                job_title=raw_job.title,
                match_score=app.match_score,
                outcome=OutcomeSignal.no_response,
                tenant_db=tenant_db,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("ml.feedback_record_failed", error=str(exc))

    return receipt


async def transition_status(
    application_id: str,
    new_status: ApplicationStatus,
    tenant_db: AsyncSession,
    note: Optional[str] = None,
) -> None:
    """FSM-guarded status transition with audit log entry."""
    result = await tenant_db.execute(
        select(JobApplication).where(JobApplication.id == application_id)
    )
    app = result.scalar_one()
    current = app.status

    allowed = _VALID_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise ValueError(
            f"Invalid transition: {current.value!r} → {new_status.value!r}. "
            f"Allowed: {[s.value for s in allowed]}"
        )

    app.status = new_status
    if new_status == ApplicationStatus.applied and app.applied_at is None:
        app.applied_at = datetime.now(timezone.utc)

    log_entry = ApplicationStatusLog(
        application_id=application_id,
        from_status=current.value,
        to_status=new_status.value,
        note=note,
    )
    tenant_db.add(log_entry)
    await tenant_db.commit()
    logger.info(
        "application.status_changed",
        application_id=application_id,
        from_status=current.value,
        to_status=new_status.value,
    )


async def queue_for_hitl(
    user_id: str,
    job_id: str,
    match_score: float,
    portal: str,
    portal_job_id: str,
    job_title: str,
    company: str,
    tenant_db: AsyncSession,
) -> str:
    """Create a pending_hitl application record and notify the user."""
    app = JobApplication(
        matched_job_id=job_id,
        portal=portal,
        portal_job_id=portal_job_id,
        job_title=job_title,
        company=company,
        match_score=match_score,
        status=ApplicationStatus.pending_hitl,
    )
    tenant_db.add(app)
    await tenant_db.flush()

    log_entry = ApplicationStatusLog(
        application_id=app.id,
        from_status=None,
        to_status=ApplicationStatus.pending_hitl.value,
        note="queued for human review",
    )
    tenant_db.add(log_entry)
    await tenant_db.commit()

    audit(
        "application.queued_hitl",
        user_id=user_id,
        details={"job_id": job_id, "application_id": app.id, "match_score": match_score},
    )

    # Fire notification (non-blocking; Phase 4 implements full dispatch)
    try:
        from app.tasks.notify import dispatch_activity_digest
        dispatch_activity_digest.delay(user_id)
    except Exception:
        pass

    logger.info("application.hitl_queued", user_id=user_id, application_id=app.id)
    return app.id
