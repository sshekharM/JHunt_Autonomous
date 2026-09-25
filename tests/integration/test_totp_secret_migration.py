"""
CHG-005 AC6/AC7 on real PostgreSQL: migration 0004 encrypts existing TOTP
secrets with the app's FERNET_KEY, and downgrading to 0003 restores the exact
plaintext. Runs only when RUN_DB_TESTS=1 (the CI "integration" job).
"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1",
    reason="needs a live PostgreSQL; set RUN_DB_TESTS=1 and POSTGRES_* env vars",
)

ROOT = Path(__file__).resolve().parents[2]
USERS = {"u-live": "JBSWY3DPEHPK3PXP", "u-anon": ""}
ADMINS = {"a-live": "KRSXG5CTMVRXEZLU"}

SEED_USER = (
    "INSERT INTO users (id, email_hash, email_encrypted, thumbprint, schema_name,"
    " oauth_provider, oauth_sub, totp_secret)"
    " VALUES (:id, :id, '\\x00', :id, :id, 'google', :id, :secret)"
)
SEED_ADMIN = (
    "INSERT INTO admin_users (id, email_hash, email_encrypted, role, totp_secret,"
    " full_name_encrypted, hashed_password)"
    " VALUES (:id, :id, '\\x00', 'ops_admin', :secret, '\\x00', 'x')"
)


def _alembic(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, check=True,
                   capture_output=True, text=True)


async def _sql(statements):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import settings
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            results = [await conn.execute(text(sql), params) for sql, params in statements]
            return [r.all() if r.returns_rows else None for r in results]
    finally:
        await engine.dispose()


def _seed():
    asyncio.run(_sql(
        [(SEED_USER, {"id": k, "secret": v}) for k, v in USERS.items()]
        + [(SEED_ADMIN, {"id": k, "secret": v}) for k, v in ADMINS.items()]))


def _read(column):
    users, admins = asyncio.run(_sql([
        (f"SELECT id, {column} FROM users", {}),  # fixed column names
        (f"SELECT id, {column} FROM admin_users", {}),
    ]))
    return dict(users), dict(admins)


def test_0004_encrypts_secrets_and_downgrade_restores_them():
    from app.security.encryption import decrypt
    _alembic("upgrade", "0003")
    try:
        _seed()
        _alembic("upgrade", "0004")
        users, admins = _read("totp_secret_encrypted")
        assert bytes(users["u-anon"]) == b""
        assert decrypt(bytes(users["u-live"])) == USERS["u-live"]
        assert {k: decrypt(bytes(v)) for k, v in admins.items()} == ADMINS

        _alembic("downgrade", "0003")
        assert _read("totp_secret") == (USERS, ADMINS)
    finally:
        _alembic("downgrade", "base")
