"""
Celery tasks for autonomous job application.
"""
import asyncio
from datetime import datetime, date, timezone

import structlog
from sqlalchemy import select, func

from app.database import AsyncSessionLocal, get_tenant_db
from app.models.user import User
from app.tasks.celery_app import celery_app

logger = structlog.get_logger("tasks.auto_apply")


def _run(coro):
    """Run an async coroutine from a sync Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(bind=True, max_retries=3)
def auto_apply_for_all_users(self):
    """Dispatch per-user apply tasks for every active user with auto_apply enabled."""
    async def _inner():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.is_active == True, User.onboarding_complete == True)
            )
            users = result.scalars().all()

        count = 0
        for user in users:
            apply_matched_jobs.delay(user.id, user.schema_name)
            count += 1

        logger.info("auto_apply.dispatched", user_count=count)

    try:
        _run(_inner())
    except Exception as exc:
        logger.error("auto_apply.dispatch_error", error=str(exc))
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=2)
def apply_matched_jobs(self, user_id: str, schema_name: str):
    """
    For one user:
      1. Check pause / auto_apply enabled.
      2. Enforce daily cap.
      3. For each matched job above threshold (sorted by score desc):
         - HITL mode → queue_for_hitl
         - Auto mode → tailored resume + cover letter → apply_to_job
    """
    async def _inner():
        from app.tenant_models.profile import UserPreferences
        from app.tenant_models.job import MatchedJob
        from app.tenant_models.application import JobApplication, ApplicationStatus
        from app.services import resume_service, cover_letter_service, application_service
        from app.security.encryption import decrypt

        async with AsyncSessionLocal() as shared_db:
            # Tenant session
            async for tenant_db in get_tenant_db(schema_name):
                # Load preferences
                pref_result = await tenant_db.execute(select(UserPreferences))
                prefs = pref_result.scalar_one_or_none()
                if prefs is None:
                    logger.info("auto_apply.no_prefs", user_id=user_id)
                    return

                if not prefs.auto_apply_enabled:
                    logger.info("auto_apply.disabled", user_id=user_id)
                    return

                # Check pause
                now = datetime.now(timezone.utc)
                if prefs.auto_apply_paused:
                    if prefs.pause_until is None or prefs.pause_until > now:
                        logger.info("auto_apply.paused", user_id=user_id)
                        return
                    # Pause expired — clear it
                    prefs.auto_apply_paused = False
                    prefs.pause_until = None
                    await tenant_db.commit()

                # Count today's applications
                today_start = datetime.combine(date.today(), datetime.min.time()).replace(
                    tzinfo=timezone.utc
                )
                count_result = await tenant_db.execute(
                    select(func.count()).where(
                        JobApplication.applied_at >= today_start,
                        JobApplication.status.not_in([
                            ApplicationStatus.pending_hitl,
                            ApplicationStatus.failed_portal_error,
                            ApplicationStatus.failed_missing_info,
                            ApplicationStatus.failed_low_match,
                        ]),
                    )
                )
                applied_today = count_result.scalar_one()
                remaining_cap = prefs.apply_cap_daily - applied_today
                if remaining_cap <= 0:
                    logger.info("auto_apply.cap_reached", user_id=user_id, cap=prefs.apply_cap_daily)
                    return

                # Get matched jobs not yet applied, above threshold, sorted by score
                applied_job_ids_result = await tenant_db.execute(
                    select(JobApplication.matched_job_id)
                )
                applied_job_ids = {r[0] for r in applied_job_ids_result.fetchall()}

                jobs_result = await tenant_db.execute(
                    select(MatchedJob)
                    .where(
                        MatchedJob.is_active == True,
                        MatchedJob.match_score >= prefs.match_threshold,
                        MatchedJob.id.not_in(applied_job_ids) if applied_job_ids else True,
                    )
                    .order_by(MatchedJob.match_score.desc())
                    .limit(remaining_cap)
                )
                jobs = jobs_result.scalars().all()

                if not jobs:
                    logger.info("auto_apply.no_jobs", user_id=user_id)
                    return

                # Load user profile for resume / cover letter generation
                from app.tenant_models.profile import UserProfile
                from app.tenant_models.resume import MasterResume
                profile_result = await tenant_db.execute(select(UserProfile))
                profile = profile_result.scalar_one_or_none()

                master_resume_result = await tenant_db.execute(
                    select(MasterResume).where(MasterResume.is_active == True)
                )
                master_resume = master_resume_result.scalar_one_or_none()

                llm_choice = prefs.llm_choice.value

                for job in jobs:
                    try:
                        if prefs.hitl_enabled:
                            await application_service.queue_for_hitl(
                                user_id=user_id,
                                job_id=job.id,
                                match_score=job.match_score,
                                portal=job.portal,
                                portal_job_id=job.portal_job_id,
                                job_title=job.title,
                                company=job.company,
                                tenant_db=tenant_db,
                            )
                            continue

                        if master_resume is None:
                            logger.warning("auto_apply.no_master_resume", user_id=user_id)
                            break

                        # Parse master resume text
                        master_text = await resume_service.parse_master_resume(
                            master_resume.minio_key
                        )

                        # Build user skills list from profile
                        from app.tenant_models.skill import UserSkill
                        skills_result = await tenant_db.execute(select(UserSkill))
                        skill_rows = skills_result.scalars().all()
                        user_skills = [s.skill_name for s in skill_rows]

                        job_dict = {
                            "title": job.title,
                            "description": job.description_snippet or "",
                            "skills_required": [],
                        }

                        tailored = await resume_service.generate_tailored_resume(
                            master_text=master_text,
                            job=job_dict,
                            user_skills=user_skills,
                            user_llm_choice=llm_choice,
                        )
                        tailored["name"] = (
                            decrypt(profile.full_name_encrypted).decode()
                            if profile
                            else "Candidate"
                        )

                        minio_key = await resume_service.render_tailored_pdf(
                            resume_data=tailored,
                            schema_name=schema_name,
                            job_id=job.id,
                        )
                        tailored_resume_id = await resume_service.store_tailored_resume(
                            user_id=user_id,
                            job_id=job.id,
                            pdf_minio_key=minio_key,
                            llm_choice=llm_choice,
                            tenant_db=tenant_db,
                        )

                        user_profile_dict = {
                            "name": tailored["name"],
                            "current_role": profile.current_role if profile else "",
                            "years_exp": profile.years_experience if profile else 0,
                        }
                        matched_skills = list(
                            set(tailored.get("skills", [])) & set(user_skills)
                        )
                        cover_letter = await cover_letter_service.generate_cover_letter(
                            user_profile=user_profile_dict,
                            job={"title": job.title, "company": job.company, "description": job.description_snippet or ""},
                            matched_skills=matched_skills,
                            user_llm_choice=llm_choice,
                        )

                        await application_service.apply_to_job(
                            user_id=user_id,
                            job_id=job.id,
                            schema_name=schema_name,
                            tenant_db=tenant_db,
                            shared_db=shared_db,
                            resume_path=minio_key,
                            cover_letter=cover_letter,
                            job_record=job,
                        )

                    except Exception as exc:
                        logger.error(
                            "auto_apply.job_error",
                            user_id=user_id,
                            job_id=job.id,
                            error=str(exc),
                        )
                        continue

    try:
        _run(_inner())
    except Exception as exc:
        logger.error("apply_matched_jobs.error", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc, countdown=120)
