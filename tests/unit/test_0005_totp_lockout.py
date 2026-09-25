"""
CHG-006 AC8: migration 0005 adds the TOTP lockout columns to users and its
downgrade removes them again. Runs upgrade/downgrade on an in-memory SQLite
copy of the table; tests/integration/test_shared_migrations.py checks the
PostgreSQL types against the models when RUN_DB_TESTS=1.
"""
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0005_totp_lockout.py"
NEW = {"totp_failed_attempts", "totp_locked_until", "totp_last_used_step"}


def _load():
    spec = importlib.util.spec_from_file_location("migration_0005", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mig = _load()


def _engine():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO users (id) VALUES ('existing')"))
    return engine


def _run(engine, step):
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


def _columns(engine):
    return {c["name"]: c for c in sa.inspect(engine).get_columns("users")}


def test_revision_chain():
    assert mig.revision == "0005" and mig.down_revision == "0004"


def test_upgrade_adds_the_counters_and_existing_rows_start_at_zero():
    engine = _engine()
    _run(engine, mig.upgrade)

    columns = _columns(engine)
    assert columns["totp_failed_attempts"]["nullable"] is False
    assert isinstance(columns["totp_failed_attempts"]["type"], sa.Integer)
    assert columns["totp_locked_until"]["nullable"] is True
    assert isinstance(columns["totp_locked_until"]["type"], sa.DateTime)
    assert columns["totp_last_used_step"]["nullable"] is True
    assert isinstance(columns["totp_last_used_step"]["type"], sa.BigInteger)
    with engine.connect() as conn:
        row = conn.execute(sa.text(
            "SELECT totp_failed_attempts, totp_locked_until, totp_last_used_step FROM users"
        )).one()
    assert tuple(row) == (0, None, None)


def test_downgrade_removes_exactly_what_upgrade_added():
    engine = _engine()
    _run(engine, mig.upgrade)
    _run(engine, mig.downgrade)

    assert set(_columns(engine)) == {"id"}
