"""Phase 4 task — stub in Phase 1."""
from app.tasks.celery_app import celery_app
import structlog

logger = structlog.get_logger("tasks.ml_retrain")


@celery_app.task
def retrain_all_user_models():
    """Retrain per-user ML models based on accumulated feedback."""
    logger.info("ml_retrain.stub", note="Phase 4 implementation pending")
