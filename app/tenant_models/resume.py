import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.tenant_models.profile import TenantBase


class MasterResume(TenantBase):
    __tablename__ = "master_resume"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    minio_key: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(256))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TailoredResume(TenantBase):
    __tablename__ = "tailored_resumes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(String(36), index=True)
    minio_key: Mapped[str] = mapped_column(String(512))
    llm_choice_used: Mapped[str] = mapped_column(String(32))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Purge policy: set to True once retention window passes (24h at scale)
    purged: Mapped[bool] = mapped_column(Boolean, default=False)
