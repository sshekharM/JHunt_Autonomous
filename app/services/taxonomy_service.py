"""
Taxonomy service — skill lookup backed by the shared skill_taxonomy table.
Seeds from data/taxonomy/it_skills.json on first run if the table is empty.
"""
import json
import os
from pathlib import Path
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.skill_taxonomy import SkillTaxonomy, TaxonomyStatus, TaxonomySource
from app.security.audit_log import audit
import structlog

logger = structlog.get_logger("services.taxonomy_service")

_SEED_FILE = Path(__file__).parent.parent.parent / "data" / "taxonomy" / "it_skills.json"

_skill_cache: Optional[list[str]] = None


async def get_all_active_skills(db: AsyncSession, use_cache: bool = True) -> list[str]:
    """
    Return all active skill names from the taxonomy table.
    In-process cache is invalidated when skills are added/updated.
    """
    global _skill_cache
    if use_cache and _skill_cache is not None:
        return _skill_cache

    result = await db.execute(
        select(SkillTaxonomy.skill_name)
        .where(SkillTaxonomy.status == TaxonomyStatus.active)
        .order_by(SkillTaxonomy.skill_name)
    )
    skills = [row[0] for row in result.fetchall()]

    if not skills:
        skills = await seed_from_file(db)

    _skill_cache = skills
    return skills


def invalidate_cache() -> None:
    global _skill_cache
    _skill_cache = None


async def seed_from_file(db: AsyncSession) -> list[str]:
    """
    Load it_skills.json and insert all entries as active taxonomy records.
    Idempotent — uses INSERT ... ON CONFLICT DO NOTHING.
    """
    if not _SEED_FILE.exists():
        logger.warning("taxonomy_service.seed_file_missing", path=str(_SEED_FILE))
        return []

    with open(_SEED_FILE) as f:
        data = json.load(f)

    skills_added = []
    for entry in data:
        skill_name = entry.get("skill_name", "").strip()
        if not skill_name:
            continue
        existing = await db.execute(
            select(SkillTaxonomy).where(SkillTaxonomy.skill_name == skill_name)
        )
        if existing.scalar_one_or_none() is not None:
            skills_added.append(skill_name)
            continue

        row = SkillTaxonomy(
            skill_name=skill_name,
            category=entry.get("category", "General"),
            subcategory=entry.get("subcategory"),
            source=TaxonomySource(entry.get("source", "manual")),
            status=TaxonomyStatus.active,
            description=entry.get("description"),
            esco_uri=entry.get("esco_uri"),
            onet_code=entry.get("onet_code"),
        )
        db.add(row)
        skills_added.append(skill_name)

    await db.commit()
    logger.info("taxonomy_service.seeded", count=len(skills_added))
    audit("taxonomy.seeded", details={"count": len(skills_added)})
    return skills_added


async def lookup_skill(skill_name: str, db: AsyncSession) -> Optional[SkillTaxonomy]:
    """Exact-match lookup by skill_name (case-insensitive)."""
    result = await db.execute(
        select(SkillTaxonomy).where(
            func.lower(SkillTaxonomy.skill_name) == skill_name.lower()
        )
    )
    return result.scalar_one_or_none()


async def add_skill(
    skill_name: str,
    category: str,
    source: TaxonomySource,
    db: AsyncSession,
    subcategory: Optional[str] = None,
    description: Optional[str] = None,
    esco_uri: Optional[str] = None,
    onet_code: Optional[str] = None,
    auto_suggested_category: Optional[str] = None,
    status: TaxonomyStatus = TaxonomyStatus.active,
) -> SkillTaxonomy:
    """
    Add a new skill to the taxonomy.
    Dynamic-discovery skills land in pending_review status so admin can approve.
    """
    row = SkillTaxonomy(
        skill_name=skill_name,
        category=category,
        subcategory=subcategory,
        source=source,
        status=status,
        description=description,
        esco_uri=esco_uri,
        onet_code=onet_code,
        auto_suggested_category=auto_suggested_category,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    invalidate_cache()
    audit("taxonomy.skill_added", details={"skill": skill_name, "source": source, "status": status})
    return row


async def get_skills_by_category(category: str, db: AsyncSession) -> list[SkillTaxonomy]:
    result = await db.execute(
        select(SkillTaxonomy)
        .where(
            SkillTaxonomy.category == category,
            SkillTaxonomy.status == TaxonomyStatus.active,
        )
        .order_by(SkillTaxonomy.skill_name)
    )
    return list(result.scalars().fetchall())


async def get_keyword_sets_for_crawling(db: AsyncSession) -> dict[str, list[str]]:
    """
    Return category -> skill list mapping used by crawlers to form search queries.
    Groups active skills by category so crawlers can rotate through topic buckets.
    """
    result = await db.execute(
        select(SkillTaxonomy.category, SkillTaxonomy.skill_name)
        .where(SkillTaxonomy.status == TaxonomyStatus.active)
        .order_by(SkillTaxonomy.category, SkillTaxonomy.skill_name)
    )
    buckets: dict[str, list[str]] = {}
    for category, skill_name in result.fetchall():
        buckets.setdefault(category, []).append(skill_name)
    return buckets
