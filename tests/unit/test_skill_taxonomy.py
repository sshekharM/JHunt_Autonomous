"""SkillTaxonomy.skill_name is unique via the migration's named constraint."""
from sqlalchemy import UniqueConstraint

from app.models.skill_taxonomy import SkillTaxonomy


def test_skill_name_unique_constraint_and_index():
    uniques = {c.name for c in SkillTaxonomy.__table__.constraints if isinstance(c, UniqueConstraint)}
    assert "uq_skill_taxonomy_skill_name" in uniques
    assert SkillTaxonomy.__table__.columns["skill_name"].index is True
