"""
Per-user schema models — all tables live in the user's private PostgreSQL schema.
These are NOT registered in the shared Base metadata; they are created via
per-schema Alembic migrations.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Boolean, DateTime, LargeBinary,
    Enum as SAEnum, ARRAY, JSON, Float, Text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import enum


class TenantBase(DeclarativeBase):
    """Separate declarative base for per-user-schema models."""
    pass


class WFHPreference(str, enum.Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"
    any = "any"


class LLMChoice(str, enum.Enum):
    self_hosted = "self_hosted"
    api = "api"


class NotificationPlatform(str, enum.Enum):
    telegram = "telegram"
    discord = "discord"


class StatusCheckFrequency(int, enum.Enum):
    every_6h = 6
    every_12h = 12
    every_18h = 18
    every_24h = 24


class UserProfile(TenantBase):
    __tablename__ = "profile"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # PII — Fernet-encrypted
    full_name_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    phone_encrypted: Mapped[bytes] = mapped_column(LargeBinary)

    # Non-PII
    city: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(128))
    current_role: Mapped[str] = mapped_column(String(256))
    years_experience: Mapped[int] = mapped_column(Integer)

    # Work & education stored as JSONB
    work_history: Mapped[dict] = mapped_column(JSON, default=list)
    education: Mapped[dict] = mapped_column(JSON, default=list)

    # Avatar from OAuth
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class UserPreferences(TenantBase):
    __tablename__ = "preferences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    desired_roles: Mapped[list] = mapped_column(JSON, default=list)
    preferred_locations: Mapped[list] = mapped_column(JSON, default=list)
    salary_min_lpa: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notice_period_days: Mapped[int] = mapped_column(Integer, default=0)
    wfh_preference: Mapped[WFHPreference] = mapped_column(
        SAEnum(WFHPreference, name="wfh_pref_enum"), default=WFHPreference.any
    )

    # LLM
    llm_choice: Mapped[LLMChoice] = mapped_column(
        SAEnum(LLMChoice, name="llm_choice_enum"), default=LLMChoice.self_hosted
    )

    # Notifications
    notification_platform: Mapped[NotificationPlatform] = mapped_column(
        SAEnum(NotificationPlatform, name="notif_platform_enum"),
        default=NotificationPlatform.telegram,
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discord_channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Auto-apply settings
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hitl_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    match_threshold: Mapped[float] = mapped_column(Float, default=0.7)
    apply_cap_daily: Mapped[int] = mapped_column(Integer, default=20)
    status_check_frequency_hours: Mapped[int] = mapped_column(Integer, default=24)

    # Per-portal daily caps (JSON: {"naukri": 10, "linkedin": 5, ...})
    portal_apply_caps: Mapped[dict] = mapped_column(JSON, default=dict)

    # Company and title blacklists
    company_blacklist: Mapped[list] = mapped_column(JSON, default=list)
    title_blacklist: Mapped[list] = mapped_column(JSON, default=list)

    # Pause flag — stops auto-apply without ending portal sessions
    auto_apply_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
