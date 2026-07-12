"""Phase 3 task — stub in Phase 1."""
from app.tasks.celery_app import celery_app
import structlog

logger = structlog.get_logger("tasks.auto_apply")


@celery_app.task
def run_auto_apply_for_all():
    """Apply to matched jobs for all users who have auto-apply enabled."""
    logger.info("auto_apply.stub", note="Phase 3 implementation pending")
