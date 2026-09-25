"""User model matches the shared migrations (unique constraints, deletion schedule)."""
from sqlalchemy import DateTime, UniqueConstraint

from app.models.user import User


def test_user_has_nullable_scheduled_deletion_timestamp():
    col = User.__table__.columns["scheduled_deletion_at"]
    assert isinstance(col.type, DateTime) and col.type.timezone is True
    assert col.nullable is True


def test_user_identity_columns_are_unique_via_named_constraints():
    uniques = {c.name for c in User.__table__.constraints if isinstance(c, UniqueConstraint)}
    assert {"uq_users_email_hash", "uq_users_thumbprint", "uq_users_schema_name"} <= uniques
    cols = User.__table__.columns
    assert cols["email_hash"].index is True and cols["thumbprint"].index is True
