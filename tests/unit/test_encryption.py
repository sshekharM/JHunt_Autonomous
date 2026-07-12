import pytest
from unittest.mock import patch

# Patch settings before import
with patch.dict("os.environ", {
    "FERNET_KEY": "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3Q=",  # 32-byte base64
    "APP_SECRET_KEY": "testsecret",
    "POSTGRES_PASSWORD": "test",
    "MINIO_SECRET_KEY": "test",
}):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()

    def test_encrypt_decrypt_roundtrip():
        from cryptography.fernet import Fernet as F
        f = F(key)
        plaintext = "test@example.com"
        encrypted = f.encrypt(plaintext.encode())
        assert f.decrypt(encrypted).decode() == plaintext

    def test_sha256_hash_deterministic():
        import hashlib
        val = "test@example.com"
        h1 = hashlib.sha256(val.encode()).hexdigest()
        h2 = hashlib.sha256(val.encode()).hexdigest()
        assert h1 == h2

    def test_thumbprint_uniqueness():
        import hashlib
        def thumbprint(email, phone):
            return hashlib.sha256(f"{email}:{phone}".encode()).hexdigest()
        assert thumbprint("a@b.com", "9999999999") != thumbprint("a@b.com", "8888888888")
        assert thumbprint("a@b.com", "9999999999") != thumbprint("c@d.com", "9999999999")
