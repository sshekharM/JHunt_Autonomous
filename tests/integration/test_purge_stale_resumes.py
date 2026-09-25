"""
Stale tailored-resume purge against real tenant schemas. tailored_resumes lives
in each user's schema, so the purge must visit every tenant. MinIO is mocked
(delete_object); the database is real. Runs only when RUN_DB_TESTS=1.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1",
    reason="needs a live PostgreSQL; set RUN_DB_TESTS=1 and POSTGRES_* env vars",
)

NOW = datetime.now(timezone.utc)


def _new_schema() -> str:
    from app.security.encryption import generate_thumbprint, schema_name_from_thumbprint
    return schema_name_from_thumbprint(generate_thumbprint(f"{uuid.uuid4()}@example.com", "+910000000000"))


async def _add_resume(schema: str, key: str, age_days: int, purged: bool = False) -> None:
    from app.database import tenant_session
    from app.tenant_models.resume import TailoredResume
    async with tenant_session(schema) as db:
        db.add(TailoredResume(job_id=str(uuid.uuid4()), minio_key=key, llm_choice_used="api",
                              generated_at=NOW - timedelta(days=age_days), purged=purged))
        await db.commit()


async def _purged_keys(schema: str) -> set[str]:
    from app.database import tenant_session
    from app.tenant_models.resume import TailoredResume
    async with tenant_session(schema) as db:
        rows = await db.execute(select(TailoredResume.minio_key).where(TailoredResume.purged.is_(True)))
        return set(rows.scalars())


@pytest.fixture
async def tenants():
    from app.database import engine, provision_user_schema, validate_schema_name
    schemas = [_new_schema(), _new_schema()]
    for s in schemas:
        await provision_user_schema(s)
    yield schemas
    async with engine.begin() as conn:
        for s in schemas:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{validate_schema_name(s)}" CASCADE'))
    await engine.dispose()


async def test_purges_old_resumes_in_every_tenant_and_keeps_recent_ones(tenants):
    from app.tasks import ml_retrain
    a, b = tenants
    await _add_resume(a, f"{a}/old.pdf", age_days=10)
    await _add_resume(a, f"{a}/new.pdf", age_days=1)
    await _add_resume(b, f"{b}/old.pdf", age_days=30)
    await _add_resume(b, f"{b}/done.pdf", age_days=30, purged=True)

    delete = AsyncMock()
    with patch.object(ml_retrain.settings, "resume_retention_days", 7), \
            patch("app.services.storage_service.delete_object", delete), \
            patch.object(ml_retrain, "_tenant_schemas", AsyncMock(return_value=[a, b])):
        summary = await ml_retrain._purge_stale_resumes_async()

    assert {c.args[0] for c in delete.call_args_list} == {f"{a}/old.pdf", f"{b}/old.pdf"}
    assert await _purged_keys(a) == {f"{a}/old.pdf"}
    assert await _purged_keys(b) == {f"{b}/old.pdf", f"{b}/done.pdf"}
    assert summary == {"tenants": 2, "purged": 2, "errors": 0}
