"""phase4 columns: scheduled_deletion_at

Revision ID: 0002
Revises: 0001_initial_shared_schema
Create Date: 2026-07-12

Notes:
  - scheduled_deletion_at goes on the shared `users` table.
  - preferences.discord_channel_id is a tenant-schema column; it is created by
    the tenant chain's baseline (migrations/tenant/versions/t0001), not here.
"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001_initial_shared_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("scheduled_deletion_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "scheduled_deletion_at")
