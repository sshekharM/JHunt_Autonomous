"""
0001's downgrade drops the shared enum types through SQLAlchemy's ENUM API
(no formatted raw SQL), after dropping the tables that use them.
"""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0001_initial_shared_schema.py"
ENUMS = {
    "portal_account_health_enum", "portal_name_enum", "admin_role_enum", "taxonomy_status_enum",
    "taxonomy_source_enum", "user_tier_enum", "oauth_provider_enum",
}


def _load():
    spec = importlib.util.spec_from_file_location("migration_0001", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downgrade_drops_each_enum_type_via_enum_api():
    module = _load()
    enum_cls = MagicMock()
    with patch.object(module, "op") as op, patch.object(module.postgresql, "ENUM", enum_cls):
        module.downgrade()
    assert {c.kwargs["name"] for c in enum_cls.call_args_list} == ENUMS
    for drop in enum_cls.return_value.drop.call_args_list:
        assert drop.args == (op.get_bind.return_value,)
        assert drop.kwargs == {"checkfirst": True}
    op.execute.assert_not_called()


def test_downgrade_drops_all_six_tables():
    module = _load()
    with patch.object(module, "op") as op, patch.object(module.postgresql, "ENUM"):
        module.downgrade()
    assert op.drop_table.call_count == 6
