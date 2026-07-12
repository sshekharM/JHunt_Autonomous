"""Phase 4 task — stub in Phase 1."""
from app.tasks.celery_app import celery_app
import structlog

logger = structlog.get_logger("tasks.notify")


@celery_app.task
def dispatch_activity_digest(user_id: str):
    """Send activity digest to user via email + chosen platform."""
    logger.info("notify.dispatch.stub", user_id=user_id, note="Phase 4 implementation pending")
