import hashlib
from cryptography.fernet import Fernet
from app.config import settings

_fernet = Fernet(settings.fernet_key.encode())


def encrypt(value: str) -> bytes:
    """Fernet-encrypt a string value for storage."""
    return _fernet.encrypt(value.encode())


def decrypt(token: bytes) -> str:
    """Decrypt a Fernet-encrypted value."""
    return _fernet.decrypt(token).decode()


def sha256_hash(value: str) -> str:
    """One-way SHA-256 hash for lookup keys (email, thumbprint)."""
    return hashlib.sha256(value.encode()).hexdigest()


def generate_thumbprint(email: str, phone: str) -> str:
    """Immutable user identity thumbprint derived from email + phone."""
    combined = f"{email.lower().strip()}:{phone.strip()}"
    return sha256_hash(combined)


def schema_name_from_thumbprint(thumbprint: str) -> str:
    """Convert thumbprint to a valid PostgreSQL schema name."""
    return f"u_{thumbprint[:32]}"
