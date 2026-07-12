import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float, JSON, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.tenant_models.profile import TenantBase


class MatchedJob(TenantBase):
    """Jobs matched to this specific user (lives in user's private schema)."""
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Reference to global job (portal + portal_job_id)
    portal: Mapped[str] = mapped_column(String(32), index=True)
    portal_job_id: Mapped[str] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(512))
    company: Mapped[str] = mapped_column(String(256))
    location: Mapped[str] = mapped_column(String(256))
    job_url: Mapped[str] = mapped_column(String(1024))
    description_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ML match output
    match_score: Mapped[float] = mapped_column(Float)
    explainability: Mapped[dict] = mapped_column(JSON, default=dict)
    # {"matched": ["Python", "FastAPI"], "missing": ["Kubernetes"]}

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
