"""
app/utils/request_utils.py

Reads caller information from the incoming request: client IP and (optionally) the user id.
"""

from typing import Optional

from fastapi import Request

try:
    from jose import jwt as _jose_jwt
    from config import JWT_SECRET_KEY as _JWT_SECRET, JWT_ALGORITHM as _JWT_ALG
    _JWT_AVAILABLE = True
except Exception:
    _JWT_AVAILABLE = False


def get_client_ip(request: Request) -> str:
    if "X-Forwarded-For" in request.headers:
        return request.headers["X-Forwarded-For"].split(",")[0]
    else:
        return request.client.host

def get_optional_user_id(request: Request) -> Optional[str]:
    """
    Silently extracts `user_id` from the Bearer JWT without doing a full
    token_validation (no Redis / DB hit).  Returns None for guests or on
    any decoding failure — never raises.
    """
    if not _JWT_AVAILABLE:
        return None
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return None
        token = auth_header.split(" ", 1)[1].strip()
        payload = _jose_jwt.decode(
            token, _JWT_SECRET, algorithms=[_JWT_ALG],
            options={"verify_exp": False}   # match existing token_validation behaviour
        )
        return payload.get("user_id") or payload.get("id")
    except Exception:
        return None
