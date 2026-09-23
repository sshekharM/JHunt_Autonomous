"""
Tenant schema-name validation (app/database.py).
Schema names are interpolated into DDL / SET search_path, which cannot take
bind parameters, so every name must match the u_<32 hex> shape produced by
schema_name_from_thumbprint before it reaches SQL.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.security.encryption import generate_thumbprint, schema_name_from_thumbprint

VALID = schema_name_from_thumbprint(generate_thumbprint("a@b.com", "+919999999999"))

BAD_NAMES = [
    "",
    "public",
    "pg_catalog",
    'u_0123456789abcdef0123456789abcdef"; DROP SCHEMA public CASCADE; --',
    "u_0123456789ABCDEF0123456789ABCDEF",  # uppercase hex
    "u_0123456789abcdef0123456789abcde",  # 31 hex chars
    "u_0123456789abcdef0123456789abcdef0",  # 33 hex chars
    "u_0123456789abcdef0123456789abcdeg",  # non-hex
    "x_0123456789abcdef0123456789abcdef",
]


def test_validate_accepts_thumbprint_schema_name():
    from app.database import validate_schema_name
    assert validate_schema_name(VALID) == VALID


@pytest.mark.parametrize("name", BAD_NAMES)
def test_validate_rejects_non_tenant_names(name):
    from app.database import validate_schema_name
    with pytest.raises(ValueError, match="Invalid tenant schema name"):
        validate_schema_name(name)


def test_search_path_sql_quotes_validated_name():
    from app.database import search_path_sql
    assert str(search_path_sql(VALID)) == f'SET search_path TO "{VALID}", public'


@pytest.mark.parametrize("name", ["public", 'x"; DROP TABLE users; --'])
def test_search_path_sql_rejects_bad_name(name):
    from app.database import search_path_sql
    with pytest.raises(ValueError):
        search_path_sql(name)


@pytest.mark.asyncio
async def test_get_tenant_db_rejects_bad_name_before_any_sql():
    import app.database as database
    session = MagicMock(execute=AsyncMock(), close=AsyncMock())
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch.object(database, "AsyncSessionLocal", factory):
        with pytest.raises(ValueError):
            await database.get_tenant_db("public").__anext__()
    session.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("name,ok", [(VALID, True), ("public", False)])
async def test_provision_user_schema_validates_name(name, ok):
    import app.database as database
    conn = MagicMock(execute=AsyncMock())
    engine = MagicMock()
    engine.begin.return_value.__aenter__ = AsyncMock(return_value=conn)
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch.object(database, "engine", engine):
        if ok:
            await database.provision_user_schema(name)
            assert str(conn.execute.call_args.args[0]) == f'CREATE SCHEMA IF NOT EXISTS "{VALID}"'
        else:
            with pytest.raises(ValueError):
                await database.provision_user_schema(name)
            conn.execute.assert_not_called()
