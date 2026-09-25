"""
The shared migration chain (alembic/) must be walkable, and 0002 must only
touch shared tables — tenant tables are migrated by migrations/tenant.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def _load_0002():
    path = ROOT / "alembic" / "versions" / "0002_phase4_columns.py"
    spec = importlib.util.spec_from_file_location("migration_0002", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0002_revises_the_real_0001_revision_id():
    assert _load_0002().down_revision == "0001_initial_shared_schema"


def test_shared_chain_has_one_head_and_walks_to_base():
    from alembic.script import ScriptDirectory
    script = ScriptDirectory(str(ROOT / "alembic"))
    assert len(script.get_heads()) == 1
    revisions = [r.revision for r in script.walk_revisions()]
    assert revisions[-2:] == ["0002", "0001_initial_shared_schema"]


def test_0002_upgrade_only_alters_shared_users_table():
    module = _load_0002()
    with patch.object(module, "op") as op:
        module.upgrade()
    assert [c.args[0] for c in op.add_column.call_args_list] == ["users"]


def test_0002_downgrade_only_alters_shared_users_table():
    module = _load_0002()
    with patch.object(module, "op") as op:
        module.downgrade()
    assert [c.args[0] for c in op.drop_column.call_args_list] == ["users"]


def test_0002_adds_nullable_timezone_aware_deletion_timestamp():
    module = _load_0002()
    with patch.object(module, "op") as op:
        module.upgrade()
    column = op.add_column.call_args.args[1]
    assert column.name == "scheduled_deletion_at"
    assert column.type.timezone is True
    assert column.nullable is True
