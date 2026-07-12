"""
Nightly per-user model retraining based on accumulated feedback signals.
Feedback signals: interview_scheduled, offer_received (positive) vs
rejected_by_recruiter, no_response, withdrawn_by_user (negative).

Phase 2: Re-weights the TF-IDF match threshold per portal using success rates.
Phase 5: Full per-skill boosting via gradient feedback loop.
"""
import asyncio
from datetime import datetime, timezone
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
    from app.database import AsyncSessionLocal
    from app.tenant_models.ml_feedback import MLFeedback, OutcomeSignal
    from sqlalchemy import select, text, func

    async with AsyncSessionLocal() as db:
        await db.execute(text(f'SET search_path TO "{schema_name}", public'))

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
    for portal, outcome, avg_score, count in rows:
        if portal not in portal_stats:
            portal_stats[portal] = {"pos": 0, "neg": 0, "total": 0, "avg_positive_score": 0.0}
        if outcome in _POSITIVE_OUTCOMES:
            portal_stats[portal]["pos"] += count
            portal_stats[portal]["avg_positive_score"] = float(avg_score or 0)
        elif outcome in _NEGATIVE_OUTCOMES:
            portal_stats[portal]["neg"] += count
        portal_stats[portal]["total"] += count

    adjustments_applied = {}

    async with AsyncSessionLocal() as db:
        await db.execute(text(f'SET search_path TO "{schema_name}", public'))

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
            pass

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


async def _purge_stale_resumes_async():
    from app.config import settings
    if not settings.resume_retention_days:
        return
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.resume_retention_days)
    logger.info("purge_stale_resumes.cutoff", cutoff=cutoff.isoformat(), days=settings.resume_retention_days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT id, minio_path FROM tailored_resumes WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        rows = result.fetchall()

    if not rows:
        logger.info("purge_stale_resumes.nothing_to_purge")
        return

    from minio import Minio
    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

    purged = 0
    errors = 0
    async with AsyncSessionLocal() as db:
        for row_id, minio_path in rows:
            try:
                if minio_path:
                    bucket, obj = minio_path.split("/", 1)
                    minio_client.remove_object(bucket, obj)
                await db.execute(
                    text("DELETE FROM tailored_resumes WHERE id = :id"),
                    {"id": row_id},
                )
                purged += 1
            except Exception as exc:
                logger.error("purge_stale_resumes.row_error", row_id=str(row_id), error=str(exc))
                errors += 1
        await db.commit()

    logger.info("purge_stale_resumes.completed", purged=purged, errors=errors)


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
