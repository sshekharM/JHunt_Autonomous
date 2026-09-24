"""
CHG-003 (risk R17): signed token helpers for the pending-2FA and session flows.
Given a user id, when a pending-2FA token is minted, then it carries
purpose=totp_setup and a 10-minute lifetime, and only such a token decodes as a
pending-2FA session; a session decode refuses any purpose-bound token.
"""
from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.services.auth_service import (
    create_access_token,
    create_pending_2fa_token,
    decode_access_token,
    decode_pending_2fa_token,
    session_user_id,
)

USER_ID = "user-123"


def _status(fn, token):
    with pytest.raises(HTTPException) as exc:
        fn(token)
    return exc.value.status_code


def test_pending_token_is_purpose_bound_and_lives_ten_minutes():
    claims = decode_access_token(create_pending_2fa_token(USER_ID))

    assert claims["sub"] == USER_ID
    assert claims["purpose"] == "totp_setup"
    assert claims["exp"] - claims["iat"] == 600


def test_pending_token_decodes_to_its_user():
    assert decode_pending_2fa_token(create_pending_2fa_token(USER_ID)) == USER_ID


@pytest.mark.parametrize("token", [
    None,
    "",
    "not-a-jwt",
    create_access_token({"sub": USER_ID}),
    create_access_token({"sub": USER_ID, "purpose": "password_reset"}),
    create_access_token({"purpose": "totp_setup"}),
    create_access_token({"sub": USER_ID, "purpose": "totp_setup"}, timedelta(seconds=-1)),
], ids=["none", "empty", "garbage", "session", "wrong-purpose", "no-subject", "expired"])
def test_pending_decode_refuses_everything_else_with_401(token):
    assert _status(decode_pending_2fa_token, token) == 401


def test_session_decode_returns_the_user_of_a_session_token():
    assert session_user_id(create_access_token({"sub": USER_ID})) == USER_ID


@pytest.mark.parametrize("token", [
    create_pending_2fa_token(USER_ID),
    create_access_token({"sub": USER_ID, "purpose": ""}),
    create_access_token({"admin_sub": "admin-1"}),
    "not-a-jwt",
], ids=["pending-2fa", "empty-purpose", "no-subject", "garbage"])
def test_session_decode_refuses_purpose_bound_or_subjectless_tokens(token):
    assert _status(session_user_id, token) == 401
