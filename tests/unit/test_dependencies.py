"""
CHG-003 (risk R17) AC6: get_current_user accepts only full session tokens.
Given a JWT in the access_token cookie, when a protected route resolves the
current user, then a purpose-bound token (such as the 10-minute pending_2fa
token) is refused with 401 before any user lookup, while a normal session
token for a verified, active user still resolves to that user.

The admin dependencies in the same module are pinned alongside: an admin token
resolves only an active, 2FA-verified admin, and require_role admits only the
listed roles.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.dependencies import get_current_admin, get_current_user, require_role
from app.models.admin import AdminRole
from app.services.auth_service import create_access_token, create_pending_2fa_token

USER_ID = "user-123"
ADMIN_ID = "admin-1"


class _FakeDB:
    def __init__(self, row):
        self.row = row
        self.statements = []

    @property
    def queries(self):
        return len(self.statements)

    async def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(scalar_one_or_none=lambda: self.row)


def _sql(stmt):
    dialect = postgresql.dialect()
    return str(stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


def _user(verified=True, active=True):
    return SimpleNamespace(id=USER_ID, totp_verified=verified, is_active=active)


def _admin(verified=True, active=True, role=AdminRole.ops_admin):
    return SimpleNamespace(id=ADMIN_ID, totp_verified=verified, is_active=active, role=role)


def _status(fn, token, db):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fn(access_token=token, db=db))
    return exc.value.status_code


# --- get_current_user -------------------------------------------------------------

def test_normal_session_token_resolves_the_user_by_id():
    db = _FakeDB(_user())
    user = asyncio.run(get_current_user(access_token=create_access_token({"sub": USER_ID}), db=db))

    assert user.id == USER_ID
    assert f"users.id = '{USER_ID}'" in _sql(db.statements[0])


@pytest.mark.parametrize("token", [
    create_pending_2fa_token(USER_ID),
    create_access_token({"sub": USER_ID, "purpose": "anything"}),
    create_access_token({"admin_sub": ADMIN_ID}),
    None,
], ids=["pending-2fa", "other-purpose", "no-subject", "missing"])
def test_non_session_tokens_are_refused_before_lookup(token):
    db = _FakeDB(_user())

    assert _status(get_current_user, token, db) == 401
    assert db.queries == 0


def test_unknown_or_inactive_user_is_401():
    token = create_access_token({"sub": USER_ID})

    assert _status(get_current_user, token, _FakeDB(None)) == 401
    assert _status(get_current_user, token, _FakeDB(_user(active=False))) == 401


def test_user_without_verified_totp_is_403():
    token = create_access_token({"sub": USER_ID})

    assert _status(get_current_user, token, _FakeDB(_user(verified=False))) == 403


# --- get_current_admin ------------------------------------------------------------

def test_admin_token_resolves_the_admin_by_id():
    db = _FakeDB(_admin())
    token = create_access_token({"admin_sub": ADMIN_ID})

    assert asyncio.run(get_current_admin(access_token=token, db=db)).id == ADMIN_ID
    assert f"admin_users.id = '{ADMIN_ID}'" in _sql(db.statements[0])


@pytest.mark.parametrize("token", [None, create_access_token({"sub": USER_ID})],
                         ids=["missing", "user-token"])
def test_non_admin_tokens_are_401_before_lookup(token):
    db = _FakeDB(_admin())

    assert _status(get_current_admin, token, db) == 401
    assert db.queries == 0


@pytest.mark.parametrize("row", [None, _admin(active=False)], ids=["unknown", "inactive"])
def test_unknown_or_inactive_admin_is_401(row):
    token = create_access_token({"admin_sub": ADMIN_ID})

    assert _status(get_current_admin, token, _FakeDB(row)) == 401


def test_admin_without_verified_totp_is_403():
    token = create_access_token({"admin_sub": ADMIN_ID})

    assert _status(get_current_admin, token, _FakeDB(_admin(verified=False))) == 403


# --- require_role -----------------------------------------------------------------

def test_require_role_admits_a_listed_role():
    checker = require_role(AdminRole.super_admin, AdminRole.ops_admin)
    admin = _admin(role=AdminRole.ops_admin)

    assert asyncio.run(checker(admin=admin)) is admin


def test_require_role_refuses_an_unlisted_role_with_403():
    checker = require_role(AdminRole.super_admin)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(checker(admin=_admin(role=AdminRole.support_admin)))

    assert exc.value.status_code == 403
