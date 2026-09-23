"""AdminUser follows pii_policy.py: email and full_name are never stored in plaintext."""
from sqlalchemy import LargeBinary, String, UniqueConstraint

from app.models.admin import AdminUser

COLS = AdminUser.__table__.columns


def test_admin_has_no_plaintext_pii_columns():
    assert "email" not in COLS and "full_name" not in COLS


def test_admin_email_is_hashed_for_lookup_and_encrypted_at_rest():
    assert isinstance(COLS["email_hash"].type, String) and COLS["email_hash"].type.length == 64
    assert isinstance(COLS["email_encrypted"].type, LargeBinary)
    assert isinstance(COLS["full_name_encrypted"].type, LargeBinary)


def test_admin_email_hash_is_unique_and_indexed():
    uniques = {c.name for c in AdminUser.__table__.constraints if isinstance(c, UniqueConstraint)}
    assert "uq_admin_users_email_hash" in uniques
    assert COLS["email_hash"].index is True


def test_admin_has_password_hash():
    assert COLS["hashed_password"].type.length == 128
    assert COLS["hashed_password"].nullable is False
