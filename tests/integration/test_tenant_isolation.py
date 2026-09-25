"""
Tenant isolation against a real PostgreSQL.

Each user's data lives in a private schema selected with SET search_path, so a
wrong or stale search_path silently reads another tenant's rows instead of
erroring. Mocks cannot prove this; these tests need a live database and run only
when RUN_DB_TESTS=1 (the CI "integration" job provides a Postgres service and
points the POSTGRES_* settings at it).
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
    thumbprint = generate_thumbprint(f"{uuid.uuid4()}@example.com", "+910000000000")
    return schema_name_from_thumbprint(thumbprint)


async def _create_tenant(schema: str) -> None:
    from app.database import provision_user_schema
    await provision_user_schema(schema)  # schema + tenant tables, as at onboarding


@pytest.fixture
async def two_tenants():
    from app.database import engine, validate_schema_name
    a, b = _new_schema(), _new_schema()
    await _create_tenant(a)
    await _create_tenant(b)
    yield a, b
    async with engine.begin() as conn:
        for schema in (a, b):
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{validate_schema_name(schema)}" CASCADE'))
    await engine.dispose()  # pooled asyncpg connections are bound to this test's event loop


async def _add_application(schema: str, title: str) -> None:
    from app.database import get_tenant_db
    from app.tenant_models.application import ApplicationStatus, JobApplication
    async for db in get_tenant_db(schema):
        db.add(JobApplication(
            matched_job_id=str(uuid.uuid4()), portal="naukri", portal_job_id="nk-1",
            job_title=title, company="Acme", match_score=0.9,
            status=ApplicationStatus.pending_hitl,
        ))
        await db.commit()


async def _titles(schema: str) -> list[str]:
    from app.database import get_tenant_db
    from app.tenant_models.application import JobApplication
    async for db in get_tenant_db(schema):
        return list((await db.execute(select(JobApplication.job_title))).scalars())
    return []


async def test_tenant_sees_only_its_own_rows(two_tenants):
    a, b = two_tenants
    await _add_application(a, "A-secret-role")
    await _add_application(b, "B-secret-role")

    assert await _titles(a) == ["A-secret-role"]
    assert await _titles(b) == ["B-secret-role"]


async def test_tenant_session_does_not_leak_search_path_to_shared_sessions(two_tenants):
    """A pooled connection returned by a tenant session must not keep the tenant's
    search_path, or the next shared get_db() session reads that tenant's tables."""
    from app.database import get_db
    from app.tenant_models.application import JobApplication
    a, _ = two_tenants
    await _add_application(a, "A-secret-role")

    async for db in get_db():
        path = (await db.execute(text("SHOW search_path"))).scalar_one()
        assert a not in path
        visible = (await db.execute(
            text("SELECT count(*) FROM pg_tables WHERE tablename = :t AND schemaname = ANY(current_schemas(false))"),
            {"t": JobApplication.__tablename__},
        )).scalar_one()
        assert visible == 0


async def test_tenant_session_keeps_its_schema_after_commit(two_tenants):
    """AsyncSession releases its connection on commit; the tenant schema must be
    re-applied for the next transaction, not lost (or taken from a stale connection)."""
    from app.database import get_tenant_db
    from app.tenant_models.application import ApplicationStatus, JobApplication
    a, b = two_tenants
    await _add_application(b, "B-secret-role")
    async for db in get_tenant_db(a):
        db.add(JobApplication(
            matched_job_id=str(uuid.uuid4()), portal="naukri", portal_job_id="nk-1",
            job_title="A-role", company="Acme", match_score=0.9, status=ApplicationStatus.pending_hitl,
        ))
        await db.commit()
        titles = list((await db.execute(select(JobApplication.job_title))).scalars())
    assert titles == ["A-role"]
