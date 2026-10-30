"""
app/utils/masking.py

Masks contact details before they are shown back to the user (e.g. "OTP sent to ab*******@gmail.com").
"""


def mask_email(email: str) -> str:
    parts = email.split("@")
    return f"{parts[0][:2]}*******@{parts[1]}"


def mask_phone(phone: str) -> str:
    return f"{phone[:4]}*******{phone[-4:]}"
