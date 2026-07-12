"""
Auto-answer portal screening questions.
Strategy: exact DB lookup first; LLM fallback for unknowns; cache new answers.
"""
import hashlib
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import router as llm_router
from app.tenant_models.screening_qa import PortalScreeningAnswer

logger = structlog.get_logger("services.screening")


def _fingerprint(question: str) -> str:
    """Stable case-insensitive fingerprint for a question string."""
    return hashlib.sha256(question.strip().lower().encode()).hexdigest()[:16]


def _build_llm_prompt(question: str, portal: str, user_profile: dict) -> str:
    return (
        f"You are filling in a job application on {portal}. "
        f"Answer the following screening question truthfully based on the candidate profile below. "
        f"Give only the answer text — no explanation, no preamble.\n\n"
        f"Candidate profile:\n"
        f"  Current role: {user_profile.get('current_role', 'Not specified')}\n"
        f"  Years of experience: {user_profile.get('years_exp', 0)}\n"
        f"  Skills: {', '.join(user_profile.get('skills', []))}\n"
        f"  Location: {user_profile.get('city', '')}, {user_profile.get('state', '')}\n\n"
        f"Screening question: {question}"
    )


async def answer_screening_question(
    question: str,
    portal: str,
    user_profile: dict,
    user_llm_choice: str,
    db: AsyncSession,
) -> str:
    """
    1. Look up the question in the tenant's saved answers (case-insensitive).
    2. Fall back to LLM if not found.
    3. Cache the LLM answer for future use.
    """
    fp = _fingerprint(question)

    result = await db.execute(
        select(PortalScreeningAnswer).where(
            PortalScreeningAnswer.portal == portal,
            PortalScreeningAnswer.question_fingerprint == fp,
        )
    )
    saved = result.scalar_one_or_none()
    if saved:
        logger.info("screening.cache_hit", portal=portal, fingerprint=fp)
        return saved.answer_text

    logger.info("screening.llm_fallback", portal=portal, question_snippet=question[:80])
    prompt = _build_llm_prompt(question, portal, user_profile)
    answer = await llm_router.generate(prompt, user_llm_choice)
    answer = answer.strip()

    # Persist for future use
    new_entry = PortalScreeningAnswer(
        portal=portal,
        question_fingerprint=fp,
        question_text=question,
        answer_text=answer,
        auto_generated=True,
        user_verified=False,
    )
    db.add(new_entry)
    await db.commit()
    logger.info("screening.cached", portal=portal, fingerprint=fp)
    return answer


async def get_saved_answers(portal: str, db: AsyncSession) -> dict[str, str]:
    """Return all cached answers for the given portal keyed by question text."""
    result = await db.execute(
        select(PortalScreeningAnswer).where(PortalScreeningAnswer.portal == portal)
    )
    rows = result.scalars().all()
    return {row.question_text: row.answer_text for row in rows}
