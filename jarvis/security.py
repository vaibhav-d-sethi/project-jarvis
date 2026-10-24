"""Password hashing (stdlib scrypt) and validation. No third-party crypto needed."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re

_N, _R, _P = 2**14, 8, 1
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_BYTES = 12
MAX_PASSWORD_BYTES = 256


class AuthError(Exception):
    """Expected, user-facing authentication failure."""


def normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if len(value) > 254 or not _EMAIL_RE.fullmatch(value):
        raise AuthError("Enter a valid email address.")
    return value


def _derive(password: bytes, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password, salt=salt, n=n, r=r, p=p, dklen=32, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if not MIN_PASSWORD_BYTES <= len(raw) <= MAX_PASSWORD_BYTES:
        raise AuthError(f"Password must be {MIN_PASSWORD_BYTES}-{MAX_PASSWORD_BYTES} characters long.")
    salt = os.urandom(16)
    digest = _derive(raw, salt, _N, _R, _P)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check; malformed hashes fail closed."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _derive(password.encode("utf-8")[:MAX_PASSWORD_BYTES], base64.b64decode(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Valid hash used so unknown-email logins cost the same as real ones.
DUMMY_HASH = hash_password("jarvis-dummy-password-for-timing")
