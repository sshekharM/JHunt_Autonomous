"""Per-account TOTP lockout and replay guard (CHG-006).

The counters live on the user row, so the limit holds across IPs. Callers read
the row with SELECT ... FOR UPDATE and commit after each change.
"""
import math
from datetime import datetime, timedelta

from app.config import settings
from app.models.user import User
from app.security.audit_log import audit


def lock_seconds_left(user: User, now: datetime) -> int:
    """Whole seconds until the account may try a TOTP code again; 0 when not locked."""
    until = user.totp_locked_until
    if until is None or until <= now:
        return 0
    return math.ceil((until - now).total_seconds())


def is_replayed_step(user: User, step: int) -> bool:
    """A code for the last accepted time step, or an earlier one, is a replay."""
    last = user.totp_last_used_step
    return last is not None and step <= last


def record_failure(user: User, now: datetime) -> None:
    """Count a bad code; the one that reaches the limit locks the account."""
    user.totp_failed_attempts += 1
    if user.totp_failed_attempts >= settings.totp_max_failures:
        user.totp_failed_attempts = 0
        user.totp_locked_until = now + timedelta(minutes=settings.totp_lockout_minutes)
        audit(
            "auth.totp_lockout_started",
            user_id=user.id,
            details={"lockout_minutes": settings.totp_lockout_minutes},
        )


def record_success(user: User, step: int) -> None:
    user.totp_failed_attempts = 0
    user.totp_locked_until = None
    user.totp_last_used_step = step
