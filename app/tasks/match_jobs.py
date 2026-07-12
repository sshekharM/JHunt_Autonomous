"""Phase 2 task — stub in Phase 1."""
from app.tasks.celery_app import celery_app
import structlog

logger = structlog.get_logger("tasks.match_jobs")


@celery_app.task
def match_all_users():
    """Match newly crawled jobs to all active user profiles."""
    logger.info("match_jobs.stub", note="Phase 2 implementation pending")
