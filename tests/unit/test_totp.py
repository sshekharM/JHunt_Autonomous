import pyotp


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
