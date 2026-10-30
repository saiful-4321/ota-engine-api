"""
app/utils/masking.py

Masks contact details before they are shown back to the user (e.g. "OTP sent to ab*******@gmail.com")
and strips passenger identity data from supplier logs.
"""

import json


def mask_email(email: str) -> str:
    parts = email.split("@")
    return f"{parts[0][:2]}*******@{parts[1]}"


def mask_phone(phone: str) -> str:
    return f"{phone[:4]}*******{phone[-4:]}"


# ── Supplier logs ────────────────────────────────────────────────────────────
# Passenger identity data never goes into logs (names, birth dates, passport, phone, email).

_PII_KEYS = {
    "TravelDocument", "PersonName", "Telephone", "Email", "birthDate", "BirthDate",
    "docNumber", "Given", "Surname", "phoneNumber", "emailAddress",
}


def redact_pii(data):
    """Copy of a JSON-like structure with passenger identity fields replaced by '[REDACTED]'."""
    if isinstance(data, dict):
        return {k: "[REDACTED]" if k in _PII_KEYS else redact_pii(v) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_pii(item) for item in data]
    return data


def redact_pii_text(text: str) -> str:
    """Same for a raw JSON body; a body that is not JSON is not logged at all."""
    try:
        return json.dumps(redact_pii(json.loads(text)))
    except (TypeError, ValueError):
        return f"<{len(text or '')} bytes, not JSON — not logged>"
