"""phase4 columns: scheduled_deletion_at and discord_channel_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-12

Notes:
  - scheduled_deletion_at goes on the shared `users` table.
  - discord_channel_id goes on `preferences` which lives in each tenant schema.
    Run with -x schema=<tenant_name> for every tenant, or via run_tenant_migrations().
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Shared schema: add scheduled_deletion_at to users
    op.add_column(
        "users",
        sa.Column("scheduled_deletion_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Tenant schema: add discord_channel_id to user_preferences (preferences table)
    # This column is only applied when this migration runs against a tenant schema
    # (i.e. alembic -x schema=u_<hash> upgrade head).
    op.add_column(
        "preferences",
        sa.Column("discord_channel_id", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("preferences", "discord_channel_id")
    op.drop_column("users", "scheduled_deletion_at")
