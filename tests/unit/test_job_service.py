"""
job_service queries a user's tenant jobs table by schema-qualified name
("<schema>".jobs), so the schema name must be validated before it reaches SQL.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.security.encryption import generate_thumbprint, schema_name_from_thumbprint

VALID = schema_name_from_thumbprint(generate_thumbprint("a@b.com", "+919999999999"))
BAD = ["public", 'u_x".jobs; DROP TABLE users; --']


def _db():
    result = MagicMock()
    result.mappings.return_value.fetchall.return_value = []
    return MagicMock(execute=AsyncMock(return_value=result))


async def _matched(db, schema):
    from app.services.job_service import get_matched_jobs_for_user
    return await get_matched_jobs_for_user("user-1", schema, db)


async def _unmatched(db, schema):
    from app.services.job_service import get_unmatched_jobs
    return await get_unmatched_jobs(db, schema)


@pytest.mark.asyncio
@pytest.mark.parametrize("call", [_matched, _unmatched])
@pytest.mark.parametrize("schema", BAD)
async def test_rejects_invalid_schema_before_sql(call, schema):
    db = _db()
    with pytest.raises(ValueError):
        await call(db, schema)
    db.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("call", [_matched, _unmatched])
async def test_queries_the_validated_tenant_jobs_table(call):
    db = _db()
    assert await call(db, VALID) == []
    assert f'"{VALID}".jobs uj' in str(db.execute.call_args.args[0])


async def _stored_upsert(raw: dict):
    from sqlalchemy.dialects import postgresql

    from app.services.job_service import store_jobs
    result = MagicMock(fetchone=MagicMock(return_value=(True,)))
    db = MagicMock(execute=AsyncMock(return_value=result), commit=AsyncMock())
    await store_jobs([raw], db, "naukri")
    return db.execute.call_args.args[0].compile(dialect=postgresql.dialect())


@pytest.mark.asyncio
async def test_store_jobs_defaults_new_job_to_active_and_not_easy_apply():
    params = (await _stored_upsert({"portal_job_id": "nk-1"})).params
    assert params["is_easy_apply"] is False
    assert params["is_active"] is True


@pytest.mark.asyncio
async def test_store_jobs_keeps_crawled_easy_apply_flag():
    params = (await _stored_upsert({"portal_job_id": "nk-1", "is_easy_apply": True})).params
    assert params["is_easy_apply"] is True


@pytest.mark.asyncio
async def test_store_jobs_reactivates_job_on_recrawl():
    compiled = await _stored_upsert({"portal_job_id": "nk-1"})
    assert "is_active = %(param_1)s" in str(compiled)
    assert compiled.params["param_1"] is True
