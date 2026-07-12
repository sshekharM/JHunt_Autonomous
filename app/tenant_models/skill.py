import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.tenant_models.profile import TenantBase


class UserSkill(TenantBase):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    skill_name: Mapped[str] = mapped_column(String(256), index=True)
    taxonomy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proficiency: Mapped[str] = mapped_column(String(32), default="intermediate")
    years_used: Mapped[float | None] = mapped_column(Float, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SkillMatchCache(TenantBase):
    """Cached TF-IDF vectors per user — rebuilt on skill update."""
    __tablename__ = "skill_match_cache"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tfidf_vector: Mapped[dict] = mapped_column(JSON)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
