"""
CHG-007 on real PostgreSQL: a grant recorded before migration 0006 reads as
'granted' afterwards; withdrawing appends a second row (the first is left
exactly as it was, and the FOR UPDATE lock is valid SQL on PostgreSQL); repeating the withdrawal
adds nothing; downgrading to 0005 keeps both rows. Runs only when
RUN_DB_TESTS=1 (the CI "integration" job).
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
SEED_USER = (
    "INSERT INTO users (id, email_hash, email_encrypted, thumbprint, schema_name,"
    " oauth_provider, oauth_sub, totp_secret_encrypted)"
    # empty secret = an anonymised account; 0004's downgrade must decrypt real rows
    " VALUES ('u-db', 'u-db', '\\x00', 'u-db', 'u_db', 'google', 'u-db', '')"
)
SEED_GRANT = (
    "INSERT INTO consent_records (id, user_id, consent_version, ip_address, user_agent,"
    " consented_to_data_processing, consented_to_auto_apply, consented_to_llm_processing,"
    " llm_choice, consented_at, consent_text_hash)"
    " VALUES ('c-1', 'u-db', '1.0', '198.51.100.1', 'Onboard/1', true, true, true,"
    " 'self_hosted', '2026-09-01T00:00:00+00:00', repeat('a', 64))"
)
ROWS = "SELECT id, event, consented_to_auto_apply, ip_address FROM consent_records ORDER BY consented_at"


def _alembic(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, check=True,
                   capture_output=True, text=True)


async def _with_session(work):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.config import settings
    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await work(session)
    finally:
        await engine.dispose()


def _run(work):
    return asyncio.run(_with_session(work))


async def _execute(session, sql):
    from sqlalchemy import text
    result = await session.execute(text(sql))
    await session.commit()
    return result.all() if result.returns_rows else None


async def _withdraw(session):
    from app.compliance.consent_store import withdraw_consent
    return await withdraw_consent("u-db", ["auto_apply"], "203.0.113.9", "Browser/2", session)


@pytest.fixture(autouse=True)
def _disposable_database_only():
    """This test downgrades to base (drops every shared table): never on a real DB."""
    from app.config import settings
    if not settings.postgres_db.endswith("_test"):
        pytest.fail(f"refusing to run migrations against {settings.postgres_db!r}; use a *_test DB")


def test_withdrawal_appends_a_row_and_survives_a_downgrade():
    _alembic("upgrade", "0005")
    try:
        _run(lambda s: _execute(s, SEED_USER))
        _run(lambda s: _execute(s, SEED_GRANT))
        _alembic("upgrade", "0006")
        assert _run(lambda s: _execute(s, ROWS)) == [("c-1", "granted", True, "198.51.100.1")]

        first = _run(_withdraw)
        again = _run(_withdraw)

        rows = _run(lambda s: _execute(s, ROWS))
        assert rows[0] == ("c-1", "granted", True, "198.51.100.1")
        assert rows[1][1:] == ("withdrawn", False, "203.0.113.9") and len(rows) == 2
        assert first.withdrawn == ("auto_apply",) and again.withdrawn == ()

        _alembic("downgrade", "0005")
        assert len(_run(lambda s: _execute(s, "SELECT id FROM consent_records"))) == 2
    finally:
        _alembic("downgrade", "base")
