"""
Phase 2 crawler tasks — stubs in Phase 1.
Celery Beat triggers these; actual crawler logic added in Phase 2.
"""
from app.tasks.celery_app import celery_app
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("tasks.crawl_jobs")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def crawl_portal(self, portal_name: str):
    """
    Crawl a specific portal for Indian IT jobs using the system account.
    Phase 2 implementation: imports the appropriate crawler class.
    """
    logger.info("crawl_portal.started", portal=portal_name)
    try:
        # Phase 2: from app.crawlers.{portal_name} import crawler; crawler.run()
        logger.info("crawl_portal.stub", portal=portal_name, note="Phase 2 implementation pending")
        audit("crawl.triggered", details={"portal": portal_name})
    except Exception as exc:
        logger.error("crawl_portal.failed", portal=portal_name, error=str(exc))
        raise self.retry(exc=exc)
