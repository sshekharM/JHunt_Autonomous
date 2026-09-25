from datetime import datetime, timedelta, timezone

import pyotp
import pytest

from app.security.totp import matched_totp_step


def test_totp_verify_valid_code():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()
    assert totp.verify(code, valid_window=1)


def test_totp_verify_wrong_code():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    assert not totp.verify("000000", valid_window=1)


def test_totp_provisioning_uri():
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri("user@test.com", issuer_name="jH_ANS")
    assert "jH_ANS" in uri
    assert "user%40test.com" in uri or "user@test.com" in uri


# --- CHG-006: which time step a code matched -------------------------------------

SECRET = "JBSWY3DPEHPK3PXP"
AT = datetime(2026, 9, 25, 10, 0, 15, tzinfo=timezone.utc)
STEP = int(AT.timestamp()) // 30


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_a_code_within_one_step_returns_the_step_it_was_made_for(offset):
    code = pyotp.TOTP(SECRET).at(AT + timedelta(seconds=30 * offset))

    assert matched_totp_step(SECRET, code, AT) == STEP + offset


@pytest.mark.parametrize("offset", [-2, 2])
def test_a_code_two_steps_away_does_not_match(offset):
    code = pyotp.TOTP(SECRET).at(AT + timedelta(seconds=30 * offset))

    assert matched_totp_step(SECRET, code, AT) is None


@pytest.mark.parametrize("code", ["", "000000x", "12345"])
def test_malformed_codes_do_not_match(code):
    assert matched_totp_step(SECRET, code, AT) is None
