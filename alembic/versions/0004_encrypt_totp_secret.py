"""encrypt totp_secret at rest

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25

CHG-005: users.totp_secret and admin_users.totp_secret held TOTP seeds in
plaintext. This moves each into totp_secret_encrypted (Fernet, FERNET_KEY from
app settings - the same key app.security.encryption uses).

Per table, in the migration's single transaction:
  1. expand   - add totp_secret_encrypted (nullable)
  2. migrate  - encrypt every row, keyset-paged in batches of BATCH_SIZE
  3. contract - make it NOT NULL and drop totp_secret

A blank secret (an anonymised user's "") maps to b"" and back, so it never
becomes a ciphertext of nothing. The downgrade runs the same steps in reverse
and restores the exact plaintext; it needs the same FERNET_KEY that ran the
upgrade.

Deploy note: expand and contract ship together (accepted for CHG-005 because
the downgrade is lossless and there is no production data yet). Code older
than this revision reads totp_secret and cannot run against the new schema,
so the app must be upgraded in the same step as the migration.
"""
from collections.abc import Callable
from functools import partial

import sqlalchemy as sa
from cryptography.fernet import Fernet
from sqlalchemy.engine import Connection

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES = ("users", "admin_users")
PLAIN = "totp_secret"
ENCRYPTED = "totp_secret_encrypted"
BATCH_SIZE = 500

Token = bytes | memoryview


def app_fernet() -> Fernet:
    from app.config import settings
    return Fernet(settings.fernet_key.encode())


def encrypt_secret(fernet: Fernet, secret: str | None) -> bytes | None:
    if secret is None:
        return None
    return fernet.encrypt(secret.encode()) if secret else b""


def decrypt_secret(fernet: Fernet, token: Token | None) -> str | None:
    if token is None:
        return None
    raw = bytes(token)
    return fernet.decrypt(raw).decode() if raw else ""


def _table(name: str) -> sa.TableClause:
    return sa.table(name, sa.column("id", sa.String), sa.column(PLAIN, sa.String),
                    sa.column(ENCRYPTED, sa.LargeBinary))


def rewrite_column(
    conn: Connection, table: str, src: str, dst: str,
    transform: Callable, batch_size: int = BATCH_SIZE,
) -> int:
    """Set dst = transform(src) on every row, keyset-paged by id. Returns rows done."""
    t = _table(table)
    update = t.update().where(t.c.id == sa.bindparam("row_id")).values(
        {dst: sa.bindparam("new_value")})
    after, done = "", 0
    while True:
        page = sa.select(t.c.id, t.c[src]).where(t.c.id > after).order_by(t.c.id).limit(batch_size)
        rows = conn.execute(page).all()
        if not rows:
            return done
        conn.execute(update, [{"row_id": r[0], "new_value": transform(r[1])} for r in rows])
        after, done = rows[-1][0], done + len(rows)


def _move(src: str, dst: str, dst_type: sa.types.TypeEngine, transform: Callable) -> None:
    for table in TABLES:
        op.add_column(table, sa.Column(dst, dst_type, nullable=True))
        rewrite_column(op.get_bind(), table, src, dst, transform)
        with op.batch_alter_table(table) as batch:
            batch.alter_column(dst, existing_type=dst_type, nullable=False)
            batch.drop_column(src)


def upgrade() -> None:
    _move(PLAIN, ENCRYPTED, sa.LargeBinary(), partial(encrypt_secret, app_fernet()))


def downgrade() -> None:
    _move(ENCRYPTED, PLAIN, sa.String(64), partial(decrypt_secret, app_fernet()))
