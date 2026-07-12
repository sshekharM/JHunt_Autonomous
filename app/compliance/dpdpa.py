"""
Digital Personal Data Protection Act (DPDPA) 2023 compliance scaffolding.
Records immutable consent at signup; provides data processing log utilities.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ConsentRecord(Base):
    """Immutable DPDPA consent log — stored in shared schema."""
    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    consent_version: Mapped[str] = mapped_column(String(16), default="1.0")
    ip_address: Mapped[str] = mapped_column(String(45))
    user_agent: Mapped[str] = mapped_column(String(512))
    # Specific consents recorded
    consented_to_data_processing: Mapped[bool] = mapped_column(Boolean)
    consented_to_auto_apply: Mapped[bool] = mapped_column(Boolean)
    consented_to_llm_processing: Mapped[bool] = mapped_column(Boolean)
    llm_choice: Mapped[str] = mapped_column(String(32))
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    consent_text_hash: Mapped[str] = mapped_column(String(64))
