"""
Deletion flows must never run DROP against a schema name that is not a
validated tenant schema — a bad name here drops the wrong schema's data.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.security.encryption import generate_thumbprint, schema_name_from_thumbprint

VALID = schema_name_from_thumbprint(generate_thumbprint("a@b.com", "+919999999999"))


def _user(schema_name: str):
    user = MagicMock()
    user.id = "user-1"
    user.schema_name = schema_name
    return user


def _db():
    return MagicMock(execute=AsyncMock(), commit=AsyncMock(), delete=AsyncMock())


async def _delete(mode_name: str, schema_name: str):
    from app.compliance import deletion
    db = _db()
    with patch.object(deletion, "audit"):
        await deletion.execute_deletion(_user(schema_name), deletion.DeletionMode(mode_name), db)
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["hard_delete", "anonymise"])
@pytest.mark.parametrize("schema", ["", "public", 'u_x"; DROP SCHEMA public CASCADE; --'])
async def test_deletion_refuses_invalid_schema_without_sql(mode, schema):
    from app.compliance import deletion
    db = _db()
    with patch.object(deletion, "audit"), pytest.raises(ValueError):
        await deletion.execute_deletion(_user(schema), deletion.DeletionMode(mode), db)
    db.execute.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_hard_delete_drops_validated_schema():
    db = await _delete("hard_delete", VALID)
    assert str(db.execute.call_args.args[0]) == f'DROP SCHEMA IF EXISTS "{VALID}" CASCADE'


@pytest.mark.asyncio
async def test_anonymise_drops_pii_tables_in_validated_schema():
    db = await _delete("anonymise", VALID)
    statements = [str(c.args[0]) for c in db.execute.call_args_list]
    assert f'DROP TABLE IF EXISTS "{VALID}"."profile" CASCADE' in statements
    assert len(statements) == 4


@pytest.mark.asyncio
async def test_anonymise_blanks_pii_on_the_user_row():
    from app.compliance import deletion
    user = _user(VALID)
    with patch.object(deletion, "audit"):
        await deletion.execute_deletion(user, deletion.DeletionMode.anonymise, _db())
    assert user.email_encrypted == b"" and user.totp_secret_encrypted == b"" and user.oauth_sub == ""
    assert user.email_hash == "anonymised_user-1" and user.is_active is False
