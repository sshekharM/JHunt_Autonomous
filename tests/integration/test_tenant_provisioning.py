"""
Tenant provisioning against a real PostgreSQL.

provision_user_schema() runs at onboarding step 1. It must leave the new user's
schema with every tenant table, stamped at the tenant migration head, and the
migrated schema must match the TenantBase models exactly. Runs only when
RUN_DB_TESTS=1 (the CI "integration" job provides PostgreSQL).
"""
import os
import uuid

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1",
    reason="needs a live PostgreSQL; set RUN_DB_TESTS=1 and POSTGRES_* env vars",
)


def _new_schema() -> str:
    from app.security.encryption import generate_thumbprint, schema_name_from_thumbprint
    return schema_name_from_thumbprint(generate_thumbprint(f"{uuid.uuid4()}@example.com", "+910000000000"))


@pytest.fixture
async def schema():
    from app.database import engine, validate_schema_name
    name = _new_schema()
    yield name
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{validate_schema_name(name)}" CASCADE'))
    await engine.dispose()  # pooled asyncpg connections are bound to this test's event loop


async def _tables_in(schema: str) -> set[str]:
    from app.database import engine
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = :s"), {"s": schema})
        return {r[0] for r in rows}


async def test_provision_creates_every_tenant_table(schema):
    from app.database import provision_user_schema
    from app.tenant_migrations import tenant_metadata
    await provision_user_schema(schema)
    assert set(tenant_metadata().tables) | {"alembic_version"} == await _tables_in(schema)


async def test_provision_stamps_schema_at_tenant_head(schema):
    from app.database import engine, provision_user_schema
    from app.tenant_migrations import tenant_head_revision
    await provision_user_schema(schema)
    async with engine.connect() as conn:
        version = (await conn.execute(text(f'SELECT version_num FROM "{schema}".alembic_version'))).scalar_one()
    assert version == tenant_head_revision()


async def test_provision_is_idempotent(schema):
    from app.database import provision_user_schema
    await provision_user_schema(schema)
    await provision_user_schema(schema)  # re-running onboarding step 1 must not fail
    assert "profile" in await _tables_in(schema)


async def test_migrated_schema_matches_tenant_models(schema):
    """No drift: the tenant migration chain must build exactly what the models declare."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database import engine, provision_user_schema, search_path_sql
    from app.tenant_migrations import tenant_metadata
    await provision_user_schema(schema)

    def diff(sync_conn):
        ctx = MigrationContext.configure(sync_conn, opts={
            "compare_type": True,
            "include_name": lambda name, type_, _: not (type_ == "table" and name == "alembic_version"),
        })
        return compare_metadata(ctx, tenant_metadata())

    async with engine.connect() as conn:
        await conn.execute(search_path_sql(schema))
        changes = await conn.run_sync(diff)
    assert changes == []


async def test_new_user_can_save_profile_after_provisioning(schema):
    """Onboarding step 1 writes a UserProfile straight after provisioning."""
    from app.database import get_tenant_db, provision_user_schema
    from app.tenant_models.profile import UserProfile
    await provision_user_schema(schema)
    async for db in get_tenant_db(schema):
        db.add(UserProfile(
            full_name_encrypted=b"x", phone_encrypted=b"y", city="Pune", state="MH",
            current_role="", years_experience=0, work_history=[], education=[],
        ))
        await db.commit()
        count = len((await db.execute(select(UserProfile))).scalars().all())
    assert count == 1
