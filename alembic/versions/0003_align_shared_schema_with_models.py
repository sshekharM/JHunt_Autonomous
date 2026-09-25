"""align shared schema with models

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23

Adds the columns the shared models use but 0001 never created:
  - admin_users.full_name_encrypted, admin_users.hashed_password
    (admin PII is Fernet-encrypted per app/security/pii_policy.py; email is
    already stored as email_hash + email_encrypted)
  - consent_records.consent_text_hash (written by compliance/consent_store.py)

The columns are NOT NULL with no default: there is no production data, and
existing admin/consent rows could not be backfilled with meaningful values,
so the upgrade fails loudly on a database that already has such rows.
"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("admin_users", sa.Column("full_name_encrypted", sa.LargeBinary, nullable=False))
    op.add_column("admin_users", sa.Column("hashed_password", sa.String(128), nullable=False))
    op.add_column("consent_records", sa.Column("consent_text_hash", sa.String(64), nullable=False))


def downgrade() -> None:
    op.drop_column("consent_records", "consent_text_hash")
    op.drop_column("admin_users", "hashed_password")
    op.drop_column("admin_users", "full_name_encrypted")
