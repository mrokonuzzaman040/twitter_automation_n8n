"""Encryption at rest for API keys and account credentials (Fernet, key derived from MASTER_KEY)."""
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from . import config


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = hashlib.pbkdf2_hmac("sha256", config.MASTER_KEY.encode(), b"social-agents-v1", 200_000)
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Could not decrypt a stored secret - MASTER_KEY has changed since it was saved")
