"""Phase 3 task — stub in Phase 1."""
from app.tasks.celery_app import celery_app
import structlog

logger = structlog.get_logger("tasks.status_check")


@celery_app.task
def check_all_application_statuses():
    """Daily re-check of application statuses per user on each portal."""
    logger.info("status_check.stub", note="Phase 3 implementation pending")
