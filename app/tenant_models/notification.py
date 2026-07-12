import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.tenant_models.profile import TenantBase
import enum


class NotificationChannel(str, enum.Enum):
    in_app = "in_app"
    email = "email"
    telegram = "telegram"
    discord = "discord"


class NotificationLog(TenantBase):
    __tablename__ = "notification_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    event_type: Mapped[str] = mapped_column(String(64))
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel, name="notif_channel_enum")
    )
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
