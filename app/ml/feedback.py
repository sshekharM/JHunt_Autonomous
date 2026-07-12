"""
Per-user ML feedback recording and automated model update.
Stores outcome signals that influence future match scoring for that user.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.tenant_models.ml_feedback import MLFeedback, OutcomeSignal
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("ml.feedback")


async def record_outcome(
    application_id: str,
    portal: str,
    job_title: str,
    match_score: float,
    outcome: OutcomeSignal,
    tenant_db: AsyncSession,
    user_id: str,
) -> None:
    """Record an outcome signal for a job application."""
    feedback = MLFeedback(
        application_id=application_id,
        portal=portal,
        job_title=job_title,
        match_score_at_apply=match_score,
        outcome=outcome,
    )
    tenant_db.add(feedback)
    await tenant_db.commit()
    audit("ml.feedback_recorded", user_id=user_id, details={"outcome": outcome, "portal": portal})


async def compute_user_score_adjustment(tenant_db: AsyncSession) -> dict:
    """
    Analyse feedback to compute per-portal and per-skill score adjustments.
    Returns a dict of adjustments used by the matcher.

    Phase 2: Simple success-rate weighting per portal.
    Phase 5: Deep per-skill feedback loop.
    """
    result = await tenant_db.execute(text("""
        SELECT portal,
               COUNT(*) FILTER (WHERE outcome IN ('interview_scheduled', 'offer_received')) AS positives,
               COUNT(*) AS total
        FROM ml_feedback
        GROUP BY portal
    """))
    adjustments = {}
    for row in result.fetchall():
        portal, positives, total = row
        if total > 0:
            success_rate = positives / total
            # Slight boost (up to +0.05) for portals with higher success rates
            adjustments[portal] = round(min(0.05, success_rate * 0.1), 4)
    return adjustments
