"""
alembic/env.py migrates the shared (public) schema only. Tenant schemas have
their own chain in migrations/tenant; a tenant mode here would run shared
migrations inside a user's schema. env.py executes migrations on import, so
it is checked statically.
"""
import ast
from pathlib import Path

ENV = Path(__file__).resolve().parents[2] / "alembic" / "env.py"


def _names() -> set[str]:
    tree = ast.parse(ENV.read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return names


def test_env_targets_shared_metadata_only():
    names = _names()
    assert "TenantBase" not in names
    assert "Base" in names


def test_env_has_no_tenant_schema_mode():
    names = _names()
    assert "get_x_argument" not in names
    assert "run_tenant_migrations" not in names


def _configure_kwargs() -> list[dict]:
    """Keyword arguments of every context.configure(...) call in env.py."""
    tree = ast.parse(ENV.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "configure"]
    return [{k.arg: k.value for k in c.keywords} for c in calls]


def test_env_compares_column_types_in_both_modes():
    configs = _configure_kwargs()
    assert len(configs) == 2  # offline + online
    for kwargs in configs:
        assert isinstance(kwargs["compare_type"], ast.Constant) and kwargs["compare_type"].value is True


def test_env_offline_mode_renders_literal_sql():
    offline = [k for k in _configure_kwargs() if "url" in k]
    assert len(offline) == 1
    assert offline[0]["literal_binds"].value is True
