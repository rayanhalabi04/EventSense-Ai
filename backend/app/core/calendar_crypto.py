import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    raw_key = settings.calendar_token_encryption_key.strip()
    if not raw_key:
        raise RuntimeError("CALENDAR_TOKEN_ENCRYPTION_KEY is required")

    try:
        return Fernet(raw_key.encode("utf-8"))
    except ValueError:
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_calendar_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_calendar_token(encrypted_token: str) -> str:
    return _fernet().decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
