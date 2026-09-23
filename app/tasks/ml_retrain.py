"""
Nightly per-user model retraining based on accumulated feedback signals.
Feedback signals: interview_scheduled, offer_received (positive) vs
rejected_by_recruiter, no_response, withdrawn_by_user (negative).

Phase 2: Re-weights the TF-IDF match threshold per portal using success rates.
Phase 5: Full per-skill boosting via gradient feedback loop.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from app.config import settings
from app.tasks.celery_app import celery_app
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("tasks.ml_retrain")

_POSITIVE_OUTCOMES = {"interview_scheduled", "offer_received"}
_NEGATIVE_OUTCOMES = {"rejected_by_recruiter", "no_response", "withdrawn_by_user"}

# Minimum feedback records needed before adjusting the model.
# Below this threshold the sample size is too small to be reliable.
MIN_FEEDBACK_SAMPLES = 5


async def _retrain_for_user(user_id: str, schema_name: str) -> dict:
    from app.database import tenant_session
    from app.tenant_models.ml_feedback import MLFeedback, OutcomeSignal
    from sqlalchemy import select, text, func

    async with tenant_session(schema_name) as db:
        result = await db.execute(
            select(
                MLFeedback.portal,
                MLFeedback.outcome,
                func.avg(MLFeedback.match_score_at_apply).label("avg_score"),
                func.count().label("count"),
            ).group_by(MLFeedback.portal, MLFeedback.outcome)
        )
        rows = result.fetchall()

    if not rows:
        return {"user_id": user_id, "status": "no_feedback"}

    # Aggregate per portal: positives, negatives, total
    portal_stats: dict[str, dict] = {}
    for portal, outcome, _avg_score, count in rows:
        if portal not in portal_stats:
            portal_stats[portal] = {"pos": 0, "neg": 0, "total": 0}
        if outcome in _POSITIVE_OUTCOMES:
            portal_stats[portal]["pos"] += count
        elif outcome in _NEGATIVE_OUTCOMES:
            portal_stats[portal]["neg"] += count
        portal_stats[portal]["total"] += count

    adjustments_applied = {}

    async with tenant_session(schema_name) as db:
        for portal, stats in portal_stats.items():
            total = stats["total"]
            if total < MIN_FEEDBACK_SAMPLES:
                continue

            success_rate = stats["pos"] / total
            # Boost: up to +0.08 for portals with high success rates
            # Penalty: up to -0.05 for portals with very low success rates
            if success_rate >= 0.5:
                adjustment = round(min(0.08, success_rate * 0.12), 4)
            else:
                adjustment = round(max(-0.05, (success_rate - 0.3) * 0.1), 4)

            adjustments_applied[portal] = adjustment

            # Persist adjustment as a note in ml_feedback metadata via a dedicated
            # JSON config row if the table supports it; for now log only so Phase 5
            # can ingest from the audit log.
            logger.info(
                "ml_retrain.adjustment_computed",
                user_id=user_id,
                portal=portal,
                success_rate=success_rate,
                adjustment=adjustment,
                total_samples=total,
            )

        # Invalidate the skill match cache so the next match run uses fresh vectors
        try:
            await db.execute(text("DELETE FROM skill_match_cache"))
            await db.commit()
        except Exception:
            logger.warning("ml_retrain.cache_invalidation_failed", user_id=user_id, exc_info=True)

    audit(
        "ml.retrained",
        user_id=user_id,
        details={
            "portals_adjusted": list(adjustments_applied.keys()),
            "adjustments": adjustments_applied,
        },
    )
    return {
        "user_id": user_id,
        "status": "ok",
        "portals": len(adjustments_applied),
        "adjustments": adjustments_applied,
    }


async def _retrain_all() -> dict:
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User.id, User.schema_name).where(
                User.is_active.is_(True),
                User.onboarding_complete.is_(True),
            )
        )
        users = result.fetchall()

    total = len(users)
    updated = 0
    failed = 0

    for user_id, schema_name in users:
        try:
            result = await _retrain_for_user(user_id, schema_name)
            if result.get("status") == "ok":
                updated += 1
        except Exception as exc:
            logger.error("ml_retrain.user_failed", user_id=user_id, error=str(exc))
            failed += 1

    summary = {"total_users": total, "updated": updated, "failed": failed}
    logger.info("ml_retrain.completed", **summary)
    audit("ml.retrain_run_completed", details=summary)
    return summary


@celery_app.task
def retrain_all_user_models():
    """Retrain per-user ML models nightly based on accumulated feedback."""
    logger.info("ml_retrain.started")
    try:
        result = asyncio.run(_retrain_all())
        return result
    except Exception as exc:
        logger.error("ml_retrain.failed", error=str(exc))
        raise


@celery_app.task
def purge_stale_resumes():
    """
    Purge tailored resumes older than resume_retention_days from MinIO and the DB.
    Controlled by settings.resume_retention_days (default 0 = disabled).
    """
    logger.info("purge_stale_resumes.started")
    try:
        asyncio.run(_purge_stale_resumes_async())
    except Exception as exc:
        logger.error("purge_stale_resumes.failed", error=str(exc))
        raise


async def _tenant_schemas() -> list[str]:
    """Schema names of every user whose tenant schema has been provisioned."""
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User.schema_name).where(User.schema_name != ""))
        return list(result.scalars())


async def _purge_tenant_resumes(schema_name: str, cutoff: datetime) -> tuple[int, int]:
    """Delete one tenant's stale tailored-resume objects and mark their rows purged
    (rows are kept: applications reference them). Returns (purged, errors)."""
    from app.database import tenant_session
    from app.services import storage_service
    from app.tenant_models.resume import TailoredResume
    from sqlalchemy import select

    purged = errors = 0
    async with tenant_session(schema_name) as db:
        stale = await db.execute(select(TailoredResume).where(
            TailoredResume.generated_at < cutoff, TailoredResume.purged.is_(False)))
        for resume in stale.scalars():
            try:
                await storage_service.delete_object(resume.minio_key)
            except Exception as exc:
                logger.error("purge_stale_resumes.object_failed", schema=schema_name, error=str(exc))
                errors += 1
                continue
            resume.purged = True
            purged += 1
        await db.commit()
    return purged, errors


async def _purge_stale_resumes_async() -> dict:
    """Purge tailored resumes older than resume_retention_days in every tenant."""
    totals = {"tenants": 0, "purged": 0, "errors": 0}
    if not settings.resume_retention_days:
        return totals
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.resume_retention_days)
    for schema_name in await _tenant_schemas():
        totals["tenants"] += 1
        try:
            purged, errors = await _purge_tenant_resumes(schema_name, cutoff)
        except Exception as exc:
            logger.error("purge_stale_resumes.tenant_failed", schema=schema_name, error=str(exc))
            totals["errors"] += 1
            continue
        totals["purged"] += purged
        totals["errors"] += errors
    logger.info("purge_stale_resumes.completed", **totals)
    return totals


@celery_app.task
def retrain_user_model(user_id: str, schema_name: str):
    """
    Retrain a single user's model immediately.
    Triggered automatically when new feedback is recorded.
    """
    logger.info("ml_retrain.single", user_id=user_id)
    try:
        result = asyncio.run(_retrain_for_user(user_id, schema_name))
        return result
    except Exception as exc:
        logger.error("ml_retrain.single_failed", user_id=user_id, error=str(exc))
        raise
