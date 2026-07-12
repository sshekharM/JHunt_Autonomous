import pyotp
import qrcode
import io
import base64
from app.config import settings


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, account_name: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=account_name,
        issuer_name=settings.totp_issuer,
    )


def generate_qr_code_base64(uri: str) -> str:
    """Return a base64-encoded PNG QR code for the TOTP URI."""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code with a 30-second window tolerance."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
