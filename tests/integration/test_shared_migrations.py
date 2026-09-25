"""
Shared (public) schema drift against a real PostgreSQL: `alembic upgrade head`
must build exactly what the shared ORM models declare. Runs only when
RUN_DB_TESTS=1 (the CI "integration" job provides PostgreSQL).

env.py runs its own event loop, so the migration is invoked as a subprocess and
this test is synchronous.
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


def _alembic(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, check=True,
                   capture_output=True, text=True)


def _shared_metadata():
    from app.database import Base
    from app.models import user, admin, portal_account, job, skill_taxonomy  # noqa: F401
    from app.compliance.dpdpa import ConsentRecord  # noqa: F401
    return Base.metadata


def _diff(sync_conn):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    ctx = MigrationContext.configure(sync_conn, opts={
        "compare_type": True,
        "include_name": lambda name, type_, _: not (type_ == "table" and name == "alembic_version"),
    })
    return compare_metadata(ctx, _shared_metadata())


async def _drift():
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.config import settings
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(_diff)
    finally:
        await engine.dispose()


def test_shared_migrations_at_head_match_models():
    _alembic("upgrade", "head")
    try:
        drift = asyncio.run(_drift())
    finally:
        _alembic("downgrade", "base")
    assert drift == []
