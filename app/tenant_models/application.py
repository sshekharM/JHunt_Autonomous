import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float, JSON, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.tenant_models.profile import TenantBase
import enum


class ApplicationStatus(str, enum.Enum):
    pending_hitl = "pending_hitl"      # queued for HITL review
    applying = "applying"              # in progress
    applied = "applied"                # successfully submitted
    viewed = "viewed"                  # recruiter viewed
    shortlisted = "shortlisted"
    interview_scheduled = "interview_scheduled"
    rejected = "rejected"
    withdrawn = "withdrawn"            # user or portal-detected withdrawal
    failed_portal_error = "failed_portal_error"
    failed_low_match = "failed_low_match"
    failed_missing_info = "failed_missing_info"


class ApplicationFailureReason(str, enum.Enum):
    portal_rejected = "portal_rejected"
    low_match_score = "low_match_score"
    missing_profile_info = "missing_profile_info"
    session_expired = "session_expired"
    unknown = "unknown"


class JobApplication(TenantBase):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    matched_job_id: Mapped[str] = mapped_column(String(36), index=True)
    portal: Mapped[str] = mapped_column(String(32))
    portal_job_id: Mapped[str] = mapped_column(String(256))
    portal_application_id: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    job_title: Mapped[str] = mapped_column(String(512))
    company: Mapped[str] = mapped_column(String(256))
    match_score: Mapped[float] = mapped_column(Float)

    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, name="app_status_enum"),
        default=ApplicationStatus.applying,
    )
    failure_reason: Mapped[ApplicationFailureReason | None] = mapped_column(
        SAEnum(ApplicationFailureReason, name="app_failure_reason_enum"),
        nullable=True,
    )
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    tailored_resume_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status_check: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ApplicationStatusLog(TenantBase):
    """Immutable append-only status change history."""
    __tablename__ = "application_status_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    from_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_status: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
