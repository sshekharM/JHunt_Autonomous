import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import enum


class TaxonomyStatus(str, enum.Enum):
    active = "active"
    pending_review = "pending_review"
    rejected = "rejected"


class TaxonomySource(str, enum.Enum):
    esco = "esco"
    onet = "onet"
    dynamic_discovery = "dynamic_discovery"
    manual = "manual"


class SkillTaxonomy(Base):
    __tablename__ = "skill_taxonomy"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    skill_name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(128))
    subcategory: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[TaxonomySource] = mapped_column(
        SAEnum(TaxonomySource, name="taxonomy_source_enum")
    )
    status: Mapped[TaxonomyStatus] = mapped_column(
        SAEnum(TaxonomyStatus, name="taxonomy_status_enum"), default=TaxonomyStatus.active
    )
    # LLM-suggested category for dynamic discoveries awaiting admin review
    auto_suggested_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    esco_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    onet_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
