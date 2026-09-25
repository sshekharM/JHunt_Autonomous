"""
Unit tests for app/tenant_migrations.py — the tenant (per-user schema)
migration chain under migrations/tenant, separate from the shared alembic/ chain.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

TENANT_TABLES = {"profile", "preferences", "applications", "application_status_log"}


def test_tenant_metadata_registers_all_tenant_models():
    from app.tenant_migrations import tenant_metadata
    from app.tenant_models.profile import TenantBase
    metadata = tenant_metadata()
    assert metadata is TenantBase.metadata
    assert TENANT_TABLES <= set(metadata.tables)


def test_tenant_metadata_excludes_shared_tables():
    from app.tenant_migrations import tenant_metadata
    assert "users" not in tenant_metadata().tables


def test_tenant_chain_lives_under_migrations_tenant():
    from app.tenant_migrations import TENANT_SCRIPT_LOCATION
    root = Path(__file__).resolve().parents[2]
    assert Path(TENANT_SCRIPT_LOCATION).resolve() == (root / "migrations" / "tenant").resolve()
    assert (Path(TENANT_SCRIPT_LOCATION) / "env.py").is_file()


def test_tenant_chain_has_exactly_one_head():
    from alembic.script import ScriptDirectory
    from app.tenant_migrations import TENANT_SCRIPT_LOCATION, tenant_head_revision
    heads = ScriptDirectory(TENANT_SCRIPT_LOCATION).get_heads()
    assert heads == [tenant_head_revision()]


@pytest.mark.asyncio
async def test_migrate_rejects_invalid_schema_before_running():
    from app.tenant_migrations import migrate_tenant_schema
    conn = MagicMock(run_sync=AsyncMock(), execute=AsyncMock())
    with pytest.raises(ValueError):
        await migrate_tenant_schema(conn, "public")
    conn.run_sync.assert_not_called()
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_upgrades_on_the_given_connection():
    from app import tenant_migrations
    from app.security.encryption import generate_thumbprint, schema_name_from_thumbprint
    schema = schema_name_from_thumbprint(generate_thumbprint("a@b.com", "+919999999999"))
    conn = MagicMock(run_sync=AsyncMock(), execute=AsyncMock())
    await tenant_migrations.migrate_tenant_schema(conn, schema)
    conn.run_sync.assert_awaited_once_with(tenant_migrations._upgrade_to_head, schema)
