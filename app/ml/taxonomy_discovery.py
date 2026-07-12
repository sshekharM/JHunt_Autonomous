"""
Dynamic skill discovery from live job descriptions.
Extracts candidate skill terms not yet in the taxonomy.
Queues them for admin review before they are added.
"""
import re
import json
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from app.models.skill_taxonomy import SkillTaxonomy, TaxonomyStatus, TaxonomySource
import structlog

logger = structlog.get_logger("ml.taxonomy_discovery")

# Common IT skill patterns — capitalised words, acronyms, known tech patterns
TECH_PATTERN = re.compile(
    r'\b([A-Z][a-zA-Z0-9+#.\-]{1,30}|[A-Z]{2,10})\b'
)

# Words to exclude (too generic)
STOPWORDS = {
    "The", "And", "Or", "For", "With", "This", "That", "From", "Into",
    "Must", "Will", "Can", "May", "Should", "You", "We", "Our", "Your",
    "Job", "Work", "Team", "Good", "Strong", "Excellent", "Years", "Year",
    "Experience", "Knowledge", "Skills", "Ability", "Understanding",
    "Minimum", "Required", "Preferred", "Desired", "Plus",
}


def extract_candidate_skills(jd_text: str, known_skills: set[str]) -> list[str]:
    """
    Extract candidate skill terms from a job description that are
    not already in the known taxonomy.
    """
    tokens = TECH_PATTERN.findall(jd_text)
    candidates = []
    for token in tokens:
        if token in STOPWORDS:
            continue
        if token.lower() not in {s.lower() for s in known_skills}:
            if len(token) > 1 and token not in candidates:
                candidates.append(token)
    return candidates[:20]  # cap at 20 per JD


async def queue_discovered_skills(
    candidate_skills: list[str],
    db: AsyncSession,
    llm_suggest_category_fn=None,
) -> int:
    """
    Add discovered skills to taxonomy as 'pending_review'.
    Skips skills already in the taxonomy.
    Returns number of new skills queued.
    """
    queued = 0
    for skill in candidate_skills:
        existing = await db.execute(
            select(SkillTaxonomy).where(
                text("LOWER(skill_name) = :name")
            ).params(name=skill.lower())
        )
        if existing.scalar_one_or_none():
            continue

        suggested_category = ""
        if llm_suggest_category_fn:
            try:
                suggested_category = await llm_suggest_category_fn(skill)
            except Exception:
                pass

        new_skill = SkillTaxonomy(
            skill_name=skill,
            category="uncategorised",
            source=TaxonomySource.dynamic_discovery,
            status=TaxonomyStatus.pending_review,
            auto_suggested_category=suggested_category,
        )
        db.add(new_skill)
        queued += 1

    if queued:
        await db.commit()
        logger.info("taxonomy_discovery.queued", count=queued)
    return queued


class SoftSignals:
    """
    SCAFFOLDED — inactive until Phase 5.
    Will factor company size, funding, brand reputation into match scoring.
    """
    enabled = False

    @staticmethod
    def score(job_extra: dict, user_preferences: dict) -> float:
        if not SoftSignals.enabled:
            return 0.0
        # Phase 5 implementation: analyse company_size, funding_stage, etc.
        raise NotImplementedError("Soft signals not yet activated.")
