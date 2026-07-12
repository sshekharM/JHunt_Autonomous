import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Enum as SAEnum, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import enum


class OAuthProvider(str, enum.Enum):
    google = "google"
    linkedin = "linkedin"
    facebook = "facebook"
    microsoft = "microsoft"  # inactive at launch — scaffold


class UserTier(str, enum.Enum):
    free = "free"
    pro = "pro"          # inactive — scaffold
    enterprise = "enterprise"  # inactive — scaffold


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # PII — hashed for lookup, encrypted for storage
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email_encrypted: Mapped[bytes] = mapped_column(LargeBinary)

    # Immutable identity thumbprint = SHA-256(email+phone)
    thumbprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # PostgreSQL schema name derived from thumbprint
    schema_name: Mapped[str] = mapped_column(String(70), unique=True)

    # OAuth
    oauth_provider: Mapped[OAuthProvider] = mapped_column(
        SAEnum(OAuthProvider, name="oauth_provider_enum")
    )
    oauth_sub: Mapped[str] = mapped_column(String(256))

    # 2FA — mandatory TOTP
    totp_secret: Mapped[str] = mapped_column(String(64))
    totp_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_step: Mapped[int] = mapped_column(default=1)

    # Tier — free at launch; pro/enterprise gates inactive
    tier: Mapped[UserTier] = mapped_column(
        SAEnum(UserTier, name="user_tier_enum"), default=UserTier.free
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
