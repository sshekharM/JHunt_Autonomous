"""
Job service — shared schema operations for crawled jobs.
Deduplication key: (portal, portal_job_id) via INSERT ON CONFLICT DO UPDATE.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.job import Job
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("services.job_service")


async def store_jobs(
    jobs: list[dict],
    db: AsyncSession,
    portal: str,
) -> dict:
    """
    Upsert a batch of raw job dicts into the shared jobs table.
    Uses INSERT ON CONFLICT DO UPDATE so re-crawled jobs refresh last_seen_at
    and any updated fields (title, skills, salary) without duplicating rows.

    Returns {"inserted": int, "updated": int}.
    """
    if not jobs:
        return {"inserted": 0, "updated": 0}

    now = datetime.now(timezone.utc)
    inserted = 0
    updated = 0

    for raw in jobs:
        values = {
            "portal": portal,
            "portal_job_id": raw["portal_job_id"],
            "title": raw.get("title", ""),
            "company": raw.get("company", ""),
            "location": raw.get("location", ""),
            "job_url": raw.get("job_url", ""),
            "description": raw.get("description", ""),
            "skills_required": raw.get("skills_required", []),
            "salary_range": raw.get("salary_range", ""),
            "experience_required": raw.get("experience_required", ""),
            "is_easy_apply": raw.get("is_easy_apply", False),
            "is_active": True,
            "extra": raw.get("extra", {}),
            "posted_at": raw.get("posted_at"),
            "crawled_at": now,
            "last_seen_at": now,
        }

        stmt = pg_insert(Job).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_job_portal_id",
            set_={
                "title": stmt.excluded.title,
                "company": stmt.excluded.company,
                "location": stmt.excluded.location,
                "job_url": stmt.excluded.job_url,
                "description": stmt.excluded.description,
                "skills_required": stmt.excluded.skills_required,
                "salary_range": stmt.excluded.salary_range,
                "experience_required": stmt.excluded.experience_required,
                "is_easy_apply": stmt.excluded.is_easy_apply,
                "is_active": True,
                "extra": stmt.excluded.extra,
                "last_seen_at": now,
            },
        ).returning(text("(xmax = 0) AS is_insert"))

        result = await db.execute(stmt)
        row = result.fetchone()
        if row and row[0]:
            inserted += 1
        else:
            updated += 1

    await db.commit()
    logger.info(
        "job_service.store_jobs",
        portal=portal,
        inserted=inserted,
        updated=updated,
        total=len(jobs),
    )
    audit("jobs.stored", details={"portal": portal, "inserted": inserted, "updated": updated})
    return {"inserted": inserted, "updated": updated}


async def get_matched_jobs_for_user(
    user_id: str,
    schema_name: str,
    db: AsyncSession,
    min_score: float = 0.0,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    Return matched jobs for a user from their tenant schema, joined with
    global job metadata to fill in any fields not stored in the tenant table.

    Queries the user's private schema `jobs` table ordered by match_score DESC.
    """
    query = text(f"""
        SELECT
            uj.id,
            uj.portal,
            uj.portal_job_id,
            uj.title,
            uj.company,
            uj.location,
            uj.job_url,
            uj.description_snippet,
            uj.match_score,
            uj.explainability,
            uj.is_active,
            uj.discovered_at,
            gj.salary_range,
            gj.experience_required,
            gj.is_easy_apply,
            gj.skills_required,
            gj.posted_at
        FROM "{schema_name}".jobs uj
        LEFT JOIN public.jobs gj
            ON gj.portal = uj.portal AND gj.portal_job_id = uj.portal_job_id
        WHERE uj.is_active = TRUE
          AND uj.match_score >= :min_score
        ORDER BY uj.match_score DESC
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(query, {"min_score": min_score, "limit": limit, "offset": offset})
    rows = result.mappings().fetchall()
    return [dict(r) for r in rows]


async def get_unmatched_jobs(
    db: AsyncSession,
    schema_name: str,
    batch_size: int = 500,
) -> list[Job]:
    """
    Return global jobs not yet present in the user's tenant schema.
    Used by match_jobs task to find new work per user.
    """
    query = text(f"""
        SELECT gj.*
        FROM public.jobs gj
        WHERE gj.is_active = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM "{schema_name}".jobs uj
              WHERE uj.portal = gj.portal
                AND uj.portal_job_id = gj.portal_job_id
          )
        ORDER BY gj.crawled_at DESC
        LIMIT :batch_size
    """)
    result = await db.execute(query, {"batch_size": batch_size})
    rows = result.mappings().fetchall()
    return [dict(r) for r in rows]


async def mark_jobs_inactive(
    portal: str,
    portal_job_ids: list[str],
    db: AsyncSession,
) -> int:
    """
    Mark jobs that are no longer live on the portal as inactive.
    Called after a full-page crawl pass to retire stale listings.
    """
    if not portal_job_ids:
        return 0
    result = await db.execute(
        text("""
            UPDATE public.jobs
            SET is_active = FALSE
            WHERE portal = :portal
              AND portal_job_id = ANY(:ids)
        """),
        {"portal": portal, "ids": portal_job_ids},
    )
    await db.commit()
    count = result.rowcount
    logger.info("job_service.mark_inactive", portal=portal, count=count)
    return count
