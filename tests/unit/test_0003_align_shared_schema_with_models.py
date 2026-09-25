"""
The shared migration chain (0001 -> head) must produce the columns the shared
models declare. Replays each upgrade() against a mocked `op` (no database) and
compares tables, columns, nullability and primary keys. Types, indexes and
constraints are checked against real PostgreSQL in
tests/integration/test_shared_migrations.py.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
CHAIN = [
    "0001_initial_shared_schema.py", "0002_phase4_columns.py",
    "0003_align_shared_schema_with_models.py", "0004_encrypt_totp_secret.py",
    "0005_totp_lockout.py",
]


def _load(name):
    spec = importlib.util.spec_from_file_location(name[:-3], VERSIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply(tables, kind, args, kwargs, batch_table):
    """Apply one recorded op call; batch ops (``with op.batch_alter_table(t)``) omit the table."""
    name = kind.rsplit(".", 1)[-1]
    table, rest = (batch_table, args) if "__enter__" in kind else (args[0] if args else None, args[1:])
    if name == "create_table":
        tables[table] = {c.name: c for c in rest if isinstance(c, sa.Column)}
    elif name == "add_column":
        tables[table][rest[0].name] = rest[0]
    elif name == "drop_column":
        tables[table].pop(rest[0])
    elif name == "alter_column" and "nullable" in kwargs:
        tables[table][rest[0]].nullable = kwargs["nullable"]


def _replay() -> dict[str, dict[str, sa.Column]]:
    tables: dict[str, dict[str, sa.Column]] = {}
    for name in CHAIN:
        module = _load(name)
        with patch.object(module, "op") as op:
            op.get_bind.return_value.execute.return_value.all.return_value = []  # empty tables
            module.upgrade()
        batch_table = None
        for call in op.mock_calls:
            kind, args, kwargs = call
            if kind == "batch_alter_table":
                batch_table = args[0]
            _apply(tables, kind, args, kwargs, batch_table)
    return tables


def _models() -> sa.MetaData:
    from app.database import Base
    from app.models import user, admin, portal_account, job, skill_taxonomy  # noqa: F401
    from app.compliance.dpdpa import ConsentRecord  # noqa: F401
    return Base.metadata


def test_0003_follows_0002():
    assert _load(CHAIN[2]).down_revision == "0002"


def test_head_has_exactly_the_model_tables_and_columns():
    migrated, models = _replay(), _models().tables
    assert set(migrated) == set(models)
    for table, model in models.items():
        assert set(migrated[table]) == set(model.columns.keys()), table


def test_head_nullability_and_primary_keys_match_models():
    migrated = _replay()
    for table, model in _models().tables.items():
        for name, col in model.columns.items():
            got = migrated[table][name]
            assert bool(got.nullable) == bool(col.nullable), f"{table}.{name} nullable"
            assert bool(got.primary_key) == bool(col.primary_key), f"{table}.{name} primary_key"


def test_0003_downgrade_removes_what_upgrade_added():
    module = _load(CHAIN[2])
    with patch.object(module, "op") as up:
        module.upgrade()
    with patch.object(module, "op") as down:
        module.downgrade()
    added = {(c.args[0], c.args[1].name) for c in up.add_column.call_args_list}
    dropped = {(c.args[0], c.args[1]) for c in down.drop_column.call_args_list}
    assert added == dropped
