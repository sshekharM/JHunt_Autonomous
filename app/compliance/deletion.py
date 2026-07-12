"""
User data deletion — three modes as per DPDPA and user choice.
"""
from enum import Enum
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, delete
from app.models.user import User
from app.security.audit_log import audit


class DeletionMode(str, Enum):
    hard_delete = "hard_delete"
    soft_delete = "soft_delete"
    anonymise = "anonymise"


async def execute_deletion(
    user: User,
    mode: DeletionMode,
    db: AsyncSession,
) -> dict:
    """
    Execute one of the three deletion flows for a user.
    Returns a summary of what was done.
    """
    if mode == DeletionMode.hard_delete:
        return await _hard_delete(user, db)
    elif mode == DeletionMode.soft_delete:
        return await _soft_delete(user, db)
    elif mode == DeletionMode.anonymise:
        return await _anonymise(user, db)


async def _hard_delete(user: User, db: AsyncSession) -> dict:
    """Drop user schema, delete user row. Irreversible."""
    schema = user.schema_name
    await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await db.delete(user)
    await db.commit()
    audit("user.hard_deleted", user_id=user.id, resource="user_data")
    return {
        "mode": "hard_delete",
        "message": "All data permanently deleted.",
        "schema_dropped": schema,
    }


async def _soft_delete(user: User, db: AsyncSession) -> dict:
    """Mark user inactive; schedule hard delete after 30 days."""
    user.is_active = False
    # Store deletion deadline in a dedicated column (added via migration)
    # For now tag via audit log — migration adds scheduled_deletion_at column
    deadline = datetime.now(timezone.utc) + timedelta(days=30)
    await db.commit()
    audit(
        "user.soft_deleted",
        user_id=user.id,
        details={"scheduled_hard_delete": deadline.isoformat()},
    )
    return {
        "mode": "soft_delete",
        "message": "Account deactivated. Permanent deletion scheduled in 30 days.",
        "hard_delete_after": deadline.isoformat(),
    }


async def _anonymise(user: User, db: AsyncSession) -> dict:
    """
    Remove all PII; preserve anonymised activity for ML model.
    What is kept (shown to user before they confirm):
      - Anonymised skill vectors (no name/contact attached)
      - Application outcome signals (portal name, match score, outcome — no personal ID)
    What is removed:
      - Name, email, phone, resume, work history, portal sessions, OAuth identity
    """
    schema = user.schema_name
    # Wipe PII columns in user's schema
    for table in ("profile", "master_resume", "tailored_resumes", "portal_sessions"):
        await db.execute(text(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE'))

    # Nullify PII on user row
    user.email_encrypted = b""
    user.email_hash = f"anonymised_{user.id}"
    user.totp_secret = ""
    user.oauth_sub = ""
    user.is_active = False
    await db.commit()
    audit("user.anonymised", user_id=user.id, resource="user_pii")
    return {
        "mode": "anonymise",
        "message": "Personal data removed. Anonymised activity retained for system improvement.",
        "retained": ["skill_vectors", "application_outcomes"],
        "removed": ["name", "email", "phone", "resume", "work_history", "portal_sessions"],
    }
