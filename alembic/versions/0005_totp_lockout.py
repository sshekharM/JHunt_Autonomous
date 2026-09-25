"""totp lockout columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-25

CHG-006: per-account TOTP lockout and replay guard. Adds to users:
  - totp_failed_attempts  integer NOT NULL, server default 0
  - totp_locked_until     timestamptz, nullable
  - totp_last_used_step   bigint, nullable

Additive only: existing rows start unlocked with a count of 0, and code older
than this revision ignores the new columns. The downgrade drops them, which
only loses in-flight lockout state.
"""
import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("totp_failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("totp_locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("totp_last_used_step", sa.BigInteger, nullable=True),
    ]


def upgrade() -> None:
    for column in _columns():
        op.add_column("users", column)


def downgrade() -> None:
    for column in reversed(_columns()):
        op.drop_column("users", column.name)
