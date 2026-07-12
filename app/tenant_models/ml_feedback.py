import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.tenant_models.profile import TenantBase
import enum


class OutcomeSignal(str, enum.Enum):
    interview_scheduled = "interview_scheduled"
    offer_received = "offer_received"
    rejected_by_recruiter = "rejected_by_recruiter"
    no_response = "no_response"
    withdrawn_by_user = "withdrawn_by_user"


class MLFeedback(TenantBase):
    __tablename__ = "ml_feedback"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    portal: Mapped[str] = mapped_column(String(32))
    job_title: Mapped[str] = mapped_column(String(512))
    match_score_at_apply: Mapped[float] = mapped_column(Float)
    outcome: Mapped[OutcomeSignal] = mapped_column(
        SAEnum(OutcomeSignal, name="outcome_signal_enum")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
