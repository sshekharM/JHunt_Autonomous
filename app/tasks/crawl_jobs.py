"""
Crawl portal tasks — runs via Celery Beat every 4 hours per portal.
Each invocation uses the system portal account, not any user's personal session.
"""
import asyncio

import structlog

from app.crawlers.registry import crawler_class_for, is_supported
from app.security.audit_log import audit
from app.tasks.celery_app import celery_app

logger = structlog.get_logger("tasks.crawl_jobs")

# Keyword sets that drive each crawl run; taxonomy_service provides the full list
# but we use a focused set for each portal call to keep runtimes bounded.
_DEFAULT_KEYWORD_GROUPS = [
    ["Python", "FastAPI", "Django"],
    ["Java", "Spring Boot", "Microservices"],
    ["React", "Node.js", "TypeScript"],
    ["AWS", "Kubernetes", "Terraform"],
    ["Machine Learning", "PyTorch", "TensorFlow"],
    ["Data Engineering", "Apache Kafka", "Apache Spark"],
    ["DevOps", "Docker", "CI/CD"],
    ["Go", "Rust", "gRPC"],
    ["PostgreSQL", "MongoDB", "Redis"],
    ["Android Development", "Flutter", "React Native"],
]


def is_known_portal(portal_name: str) -> bool:
    """True if the shared crawler registry has a crawler for this portal."""
    return is_supported(portal_name)


async def _run_crawl(portal_name: str) -> dict:
    from datetime import datetime, timezone

    from sqlalchemy import select, text

    from app.crawlers.session_manager import get_context
    from app.database import AsyncSessionLocal
    from app.models.portal_account import PortalAccountHealth, SystemPortalAccount
    from app.services.job_service import store_jobs
    from app.services.taxonomy_service import get_keyword_sets_for_crawling

    CrawlerClass = crawler_class_for(portal_name)
    crawler = CrawlerClass()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SystemPortalAccount).where(
                SystemPortalAccount.portal == portal_name,
                SystemPortalAccount.is_active.is_(True),
                SystemPortalAccount.health != PortalAccountHealth.blocked,
            )
        )
        account = result.scalar_one_or_none()

    if account is None:
        logger.warning("crawl_portal.no_active_account", portal=portal_name)
        return {"portal": portal_name, "status": "skipped", "reason": "no_active_account"}

    context = await get_context(portal_name)
    logged_in = await crawler.login(context)
    if not logged_in:
        logger.error("crawl_portal.login_failed", portal=portal_name)
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("UPDATE system_portal_accounts SET health = 'degraded' WHERE portal = :p"),
                {"p": portal_name},
            )
            await db.commit()
        return {"portal": portal_name, "status": "failed", "reason": "login_failed"}

    async with AsyncSessionLocal() as db:
        keyword_buckets = await get_keyword_sets_for_crawling(db)

    keyword_groups = list(keyword_buckets.values()) or _DEFAULT_KEYWORD_GROUPS

    total_inserted = 0
    total_updated = 0
    errors = 0

    for keyword_group in keyword_groups:
        search_kws = keyword_group[:5]  # portal search strings stay short
        try:
            raw_jobs = await crawler.search_jobs(
                context,
                keywords=search_kws,
                location="India",
            )
            if not raw_jobs:
                continue

            job_dicts = [
                {
                    "portal_job_id": j.portal_job_id,
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "job_url": j.job_url,
                    "description": j.description,
                    "skills_required": j.skills_required,
                    "salary_range": j.salary_range,
                    "experience_required": j.experience_required,
                    "is_easy_apply": j.is_easy_apply,
                    "posted_at": j.posted_at,
                    "extra": j.extra,
                }
                for j in raw_jobs
            ]

            async with AsyncSessionLocal() as db:
                store_result = await store_jobs(job_dicts, db, portal_name)
            total_inserted += store_result["inserted"]
            total_updated += store_result["updated"]

        except Exception as exc:  # noqa: BLE001 - one keyword group's failure must not stop the rest
            logger.error(
                "crawl_portal.keyword_group_failed",
                portal=portal_name,
                keywords=search_kws,
                error=str(exc),
            )
            errors += 1

    # Mark last_crawl on the account record
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        await db.execute(
            text("""
                UPDATE system_portal_accounts
                SET last_crawl = :now,
                    health = CASE WHEN health = 'degraded' THEN 'healthy' ELSE health END
                WHERE portal = :p
            """),
            {"now": now, "p": portal_name},
        )
        await db.commit()

    summary = {
        "portal": portal_name,
        "inserted": total_inserted,
        "updated": total_updated,
        "errors": errors,
    }
    audit("crawl.completed", details=summary)
    logger.info("crawl_portal.completed", **summary)

    # Trigger match_jobs for all users now that new jobs are available
    match_all_users.delay()

    return summary


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def crawl_portal(self, portal_name: str):
    """
    Crawl a specific portal for Indian IT jobs using the system account.
    Runs asynchronously inside a new event loop — Celery workers are sync.
    """
    portal_name = portal_name.lower()
    if not is_known_portal(portal_name):
        logger.error("crawl_portal.unknown_portal", portal=portal_name)
        return {"error": f"Unknown portal: {portal_name}"}

    logger.info("crawl_portal.started", portal=portal_name)
    try:
        result = asyncio.run(_run_crawl(portal_name))
        return result
    except Exception as exc:  # noqa: BLE001 - any failure must trigger a Celery retry
        logger.error("crawl_portal.failed", portal=portal_name, error=str(exc))
        audit("crawl.failed", details={"portal": portal_name, "error": str(exc)})
        raise self.retry(exc=exc)


# Imported at the bottom on purpose: a module-level import here is circular.
from app.tasks.match_jobs import match_all_users
