import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, LargeBinary, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import enum


class PortalName(str, enum.Enum):
    naukri = "naukri"
    linkedin = "linkedin"
    glassdoor = "glassdoor"
    indeed = "indeed"
    monster = "monster"
    shine = "shine"


class PortalAccountHealth(str, enum.Enum):
    healthy = "healthy"
    degraded = "degraded"
    blocked = "blocked"
    unknown = "unknown"


class SystemPortalAccount(Base):
    """System-owned service accounts used for job crawling (not user's personal accounts)."""
    __tablename__ = "system_portal_accounts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    portal: Mapped[PortalName] = mapped_column(
        SAEnum(PortalName, name="portal_name_enum"), unique=True
    )
    email_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    password_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    # Session cookies stored as Fernet-encrypted JSON string
    session_cookies_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    session_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    health: Mapped[PortalAccountHealth] = mapped_column(
        SAEnum(PortalAccountHealth, name="portal_account_health_enum"),
        default=PortalAccountHealth.unknown,
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_crawl: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
