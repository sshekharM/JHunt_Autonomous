import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.tenant_models.profile import TenantBase


class PortalScreeningAnswer(TenantBase):
    """User-specific saved answers to common portal screening questions."""
    __tablename__ = "screening_answers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    portal: Mapped[str] = mapped_column(String(32), index=True)
    question_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str] = mapped_column(Text)
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MissingInfoLog(TenantBase):
    """Fields the tool needed but couldn't find; surfaced on next user login."""
    __tablename__ = "missing_info_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    portal: Mapped[str] = mapped_column(String(32))
    field_name: Mapped[str] = mapped_column(String(128))
    field_label: Mapped[str] = mapped_column(String(256))
    encountered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
