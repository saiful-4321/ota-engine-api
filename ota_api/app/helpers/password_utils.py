# app/helpers/password_utils.py
# Shared bcrypt password hashing utility.
# Uses passlib's bcrypt (rounds=12) which produces $2b$ hashes.
# Laravel's bcrypt verifier accepts both $2b$ and $2y$ prefixes,
# making passwords generated here fully compatible with Laravel Auth.

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt truncates at 72 bytes; newer passlib versions raise an error instead
# of silently truncating. We truncate explicitly to keep behaviour predictable
# and consistent between hashing and verification.
_BCRYPT_MAX_BYTES = 72


def _bcrypt_safe(plain_password: str) -> str:
    """Return the password truncated to the bcrypt 72-byte limit."""
    encoded = plain_password.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        encoded = encoded[:_BCRYPT_MAX_BYTES]
    return encoded.decode("utf-8", errors="ignore")


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt.

    The resulting hash (e.g. $2b$12$...) is verifiable by both this
    FastAPI application and any Laravel application using the default
    bcrypt hasher (password => 'hashed' cast or Hash::make()).
    """
    return _pwd_context.hash(_bcrypt_safe(plain_password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a stored hash.

    Handles:
    - bcrypt hashes ($2b$ or $2y$) — from Laravel or this app
    - Werkzeug PBKDF2 hashes (pbkdf2:sha256:...) — legacy FastAPI hashes
      via a transparent fallback so existing users can still log in.
    """
    # Transparent fallback for legacy Werkzeug PBKDF2 hashes
    if hashed_password.startswith("pbkdf2:"):
        try:
            from werkzeug.security import check_password_hash as _werkzeug_check
            return _werkzeug_check(hashed_password, plain_password)
        except Exception:
            return False

    return _pwd_context.verify(_bcrypt_safe(plain_password), hashed_password)
