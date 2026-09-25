"""
CHG-005 AC1/AC2: the TOTP secret is personal-data-grade and is stored only
Fernet-encrypted.

Given the shared users and admin_users tables, when their columns are listed,
then the secret lives in ``totp_secret_encrypted`` (binary, required) and no
plaintext ``totp_secret`` column remains — so the PII policy no longer needs
a known-violation entry for either table.
"""
import pytest
from sqlalchemy import LargeBinary

from app.models.admin import AdminUser
from app.models.user import User
from app.security.pii_policy import KNOWN_VIOLATIONS


@pytest.mark.parametrize("model", [User, AdminUser], ids=["users", "admin_users"])
def test_totp_secret_is_stored_only_encrypted(model):
    columns = model.__table__.columns

    assert "totp_secret" not in columns
    encrypted = columns["totp_secret_encrypted"]
    assert isinstance(encrypted.type, LargeBinary) and encrypted.nullable is False


def test_totp_secret_is_no_longer_a_known_pii_violation():
    assert KNOWN_VIOLATIONS == set()
