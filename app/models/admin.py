import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Enum as SAEnum, LargeBinary, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import enum


class AdminRole(str, enum.Enum):
    super_admin = "super_admin"
    ops_admin = "ops_admin"
    content_admin = "content_admin"
    support_admin = "support_admin"


class AdminUser(Base):
    """Admin account. Per app/security/pii_policy.py, email and name are stored
    Fernet-encrypted; email_hash (sha256) is the lookup key."""

    __tablename__ = "admin_users"
    __table_args__ = (UniqueConstraint("email_hash", name="uq_admin_users_email_hash"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email_hash: Mapped[str] = mapped_column(String(64), index=True)
    email_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    full_name_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    hashed_password: Mapped[str] = mapped_column(String(128))
    role: Mapped[AdminRole] = mapped_column(
        SAEnum(AdminRole, name="admin_role_enum"), default=AdminRole.support_admin
    )
    totp_secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary)  # Fernet (CHG-005)
    totp_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
