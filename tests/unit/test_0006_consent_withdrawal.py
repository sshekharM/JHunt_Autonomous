"""
CHG-007 AC1: migration 0006 adds consent_records.event so a withdrawal can be
stored as a new row. Existing rows read as 'granted', and the downgrade removes
the column. Runs upgrade/downgrade on an in-memory SQLite copy of the table;
tests/integration/test_shared_migrations.py checks PostgreSQL when RUN_DB_TESTS=1.
"""
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0006_consent_withdrawal.py"


def _load():
    spec = importlib.util.spec_from_file_location("migration_0006", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mig = _load()


def _engine():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE consent_records (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO consent_records (id) VALUES ('existing')"))
    return engine


def _run(engine, step):
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


def _columns(engine):
    return {c["name"]: c for c in sa.inspect(engine).get_columns("consent_records")}


def test_revision_chain():
    assert mig.revision == "0006" and mig.down_revision == "0005"


def test_upgrade_adds_event_and_existing_rows_read_as_granted():
    engine = _engine()
    _run(engine, mig.upgrade)

    event = _columns(engine)["event"]
    assert event["nullable"] is False
    assert isinstance(event["type"], sa.String) and event["type"].length == 16
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO consent_records (id) VALUES ('new')"))
        rows = conn.execute(sa.text("SELECT id, event FROM consent_records ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [("existing", "granted"), ("new", "granted")]


def test_downgrade_removes_exactly_what_upgrade_added():
    engine = _engine()
    _run(engine, mig.upgrade)
    _run(engine, mig.downgrade)

    assert set(_columns(engine)) == {"id"}
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT id FROM consent_records")).scalar_one() == "existing"
