"""
Match newly crawled jobs against every active user's skill profile.
Stores results in the user's tenant schema jobs table.
Triggers notifications for high-match jobs.
"""
import asyncio
import uuid
from datetime import datetime, timezone
from app.tasks.celery_app import celery_app
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("tasks.match_jobs")

HIGH_MATCH_THRESHOLD = 0.75
DESCRIPTION_SNIPPET_LEN = 500


async def _run_match_for_user(user_id: str, schema_name: str) -> dict:
    from app.database import AsyncSessionLocal
    from app.services.job_service import get_unmatched_jobs
    from app.ml.matcher import compute_match
    from app.ml.feedback import compute_user_score_adjustment
    from sqlalchemy import select, text

    from app.tenant_models.skill import UserSkill
    from app.tenant_models.job import MatchedJob

    matched_count = 0
    high_match_count = 0

    async with AsyncSessionLocal() as shared_db:
        await shared_db.execute(text(f'SET search_path TO "{schema_name}", public'))
        result = await shared_db.execute(select(UserSkill))
        skills = result.scalars().fetchall()

    user_skills = [s.skill_name for s in skills]
    if not user_skills:
        logger.info("match_jobs.no_skills", user_id=user_id, schema=schema_name)
        return {"user_id": user_id, "matched": 0, "skipped": "no_skills"}

    async with AsyncSessionLocal() as shared_db:
        unmatched = await get_unmatched_jobs(shared_db, schema_name)

    if not unmatched:
        return {"user_id": user_id, "matched": 0, "skipped": "no_new_jobs"}

    async with AsyncSessionLocal() as tenant_db:
        await tenant_db.execute(text(f'SET search_path TO "{schema_name}", public'))
        score_adjustments = await compute_user_score_adjustment(tenant_db)

    high_match_jobs = []

    async with AsyncSessionLocal() as tenant_db:
        await tenant_db.execute(text(f'SET search_path TO "{schema_name}", public'))

        for job in unmatched:
            job_skills = job.get("skills_required") or []
            if not job_skills:
                # Jobs with no skills listed are still added with score 0
                # so they appear in the user's list as "explore" items.
                match_result = {"score": 0.0, "matched": [], "missing": [], "coverage_pct": 0.0}
            else:
                match_result = compute_match(user_skills, job_skills)

            # Apply portal-level score adjustment from feedback history
            portal = job.get("portal", "")
            adjustment = score_adjustments.get(portal, 0.0)
            adjusted_score = round(min(1.0, match_result["score"] + adjustment), 4)

            description = job.get("description", "") or ""
            snippet = description[:DESCRIPTION_SNIPPET_LEN] if description else None

            matched_job = MatchedJob(
                id=str(uuid.uuid4()),
                portal=portal,
                portal_job_id=job["portal_job_id"],
                title=job.get("title", ""),
                company=job.get("company", ""),
                location=job.get("location", ""),
                job_url=job.get("job_url", ""),
                description_snippet=snippet,
                match_score=adjusted_score,
                explainability={
                    "matched": match_result["matched"],
                    "missing": match_result["missing"],
                    "coverage_pct": match_result["coverage_pct"],
                    "portal_adjustment": adjustment,
                },
                is_active=True,
                discovered_at=datetime.now(timezone.utc),
            )
            tenant_db.add(matched_job)
            matched_count += 1

            if adjusted_score >= HIGH_MATCH_THRESHOLD:
                high_match_jobs.append({
                    "portal": portal,
                    "portal_job_id": job["portal_job_id"],
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "score": adjusted_score,
                })
                high_match_count += 1

        await tenant_db.commit()

    if high_match_jobs:
        from app.tasks.notify import send_match_notification
        send_match_notification.delay(user_id, high_match_jobs)

    return {
        "user_id": user_id,
        "matched": matched_count,
        "high_match": high_match_count,
    }


async def _run_match_all_users() -> dict:
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

    total_users = len(users)
    total_matched = 0
    failed = 0

    for user_id, schema_name in users:
        try:
            result = await _run_match_for_user(user_id, schema_name)
            total_matched += result.get("matched", 0)
            logger.info("match_jobs.user_done", **result)
        except Exception as exc:
            logger.error("match_jobs.user_failed", user_id=user_id, error=str(exc))
            audit("match.user_failed", user_id=user_id, error=exc)
            failed += 1

    summary = {
        "total_users": total_users,
        "total_matched": total_matched,
        "failed_users": failed,
    }
    audit("match.completed", details=summary)
    return summary


@celery_app.task
def match_all_users():
    """Match newly crawled jobs to all active users with completed onboarding."""
    logger.info("match_jobs.started")
    try:
        result = asyncio.run(_run_match_all_users())
        logger.info("match_jobs.completed", **result)
        return result
    except Exception as exc:
        logger.error("match_jobs.failed", error=str(exc))
        raise


@celery_app.task
def match_jobs_for_user(user_id: str, schema_name: str):
    """Match jobs for a single user — called after profile/skill update."""
    logger.info("match_jobs.single_user", user_id=user_id)
    try:
        result = asyncio.run(_run_match_for_user(user_id, schema_name))
        logger.info("match_jobs.single_user_done", **result)
        return result
    except Exception as exc:
        logger.error("match_jobs.single_user_failed", user_id=user_id, error=str(exc))
        raise
