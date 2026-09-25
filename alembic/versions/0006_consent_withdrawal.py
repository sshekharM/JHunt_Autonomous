"""consent withdrawal event column

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-25

CHG-007: consent_records stays append-only; a DPDPA withdrawal is stored as a
new row. Adds to consent_records:
  - event  varchar(16) NOT NULL, server default 'granted'

Additive only: the constant server default fills existing rows with 'granted'
(a metadata-only change on PostgreSQL 11+, no table rewrite), and code older
than this revision inserts without the column and still gets 'granted'.
The downgrade drops the column. Withdrawal rows then stay in the table with
their consent flags False, but lose the marker that says they were withdrawals.
"""
import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consent_records",
        sa.Column("event", sa.String(16), nullable=False, server_default="granted"),
    )


def downgrade() -> None:
    op.drop_column("consent_records", "event")
