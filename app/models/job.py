"""
Global jobs table — shared schema.
Stores all crawled jobs before they are matched to individual users.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("portal", "portal_job_id", name="uq_job_portal_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    portal: Mapped[str] = mapped_column(String(32), index=True)
    portal_job_id: Mapped[str] = mapped_column(String(256), index=True)
    title: Mapped[str] = mapped_column(String(512))
    company: Mapped[str] = mapped_column(String(256), index=True)
    location: Mapped[str] = mapped_column(String(256))
    job_url: Mapped[str] = mapped_column(String(1024))
    description: Mapped[str] = mapped_column(Text, default="")
    skills_required: Mapped[list] = mapped_column(JSON, default=list)
    salary_range: Mapped[str] = mapped_column(String(256), default="")
    experience_required: Mapped[str] = mapped_column(String(128), default="")
    is_easy_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
