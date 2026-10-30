"""
app/helpers/passport.py

Passport scanning for the booking form: validates the upload, rate-limits per user and forwards
the image to the internal passport_ocr microservice, whose API key never leaves the server.
The OCR response is returned unchanged. Images and passport data are never stored or logged.
"""

from typing import Dict

import requests
from fastapi import UploadFile
from fastapi.responses import JSONResponse

from app.helpers.common import write_log
from app.utils.redis_utils import redis_helper
from config import PASSPORT_OCR_API_KEY, PASSPORT_OCR_RATE_LIMIT, PASSPORT_OCR_URL

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
OCR_TIMEOUT_S = 90
UNAVAILABLE = "Passport scanning is temporarily unavailable. Please enter the details manually."
_ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/tiff", "image/heic", "image/heif", "application/pdf",
}
_LOG_SOURCE = "PassportController"


def error_response(status: int, message: str) -> JSONResponse:
    """Same error shape as the OCR service, so the frontend handles both alike."""
    return JSONResponse(status_code=status, content={"status": "error", "message": message, "hints": []})


def is_rate_limited(identity: str) -> bool:
    """Fixed one-minute window per user (or IP). Fails open if Redis is unavailable."""
    key = f"passport_ocr_rl:{identity}"
    try:
        with redis_helper._with_db_context() as client:
            count = client.incr(key)
            if count == 1:
                client.expire(key, 60)
        return count > PASSPORT_OCR_RATE_LIMIT
    except Exception as exc:
        write_log(f"Passport OCR rate limiter unavailable: {exc}", source=_LOG_SOURCE, type="warning")
        return False


def _is_allowed_type(content_type: str) -> bool:
    return not content_type or content_type in _ALLOWED_TYPES or content_type.startswith("image/")


def scan_passport(file: UploadFile, identity: str, sections: Dict[str, bool]) -> JSONResponse:
    """
    `identity` is the user id (or client IP) used for rate limiting; `sections` maps each
    include_* flag to its value and is forwarded as query parameters.
    """
    if is_rate_limited(identity):
        return error_response(429, f"Too many passport scans. Try again in a minute (limit {PASSPORT_OCR_RATE_LIMIT}/min).")

    content_type = (file.content_type or "").lower()
    if not _is_allowed_type(content_type):
        return error_response(415, "Upload a JPEG, PNG, WEBP, TIFF, HEIC image or a PDF of the passport data page")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return error_response(413, "File too large (max 10 MB)")

    try:
        resp = requests.post(
            f"{PASSPORT_OCR_URL}/v1/passport/ocr",
            params={name: str(value).lower() for name, value in sections.items()},
            files={"file": (file.filename or "passport", data, content_type or "application/octet-stream")},
            headers={"X-API-Key": PASSPORT_OCR_API_KEY},
            timeout=OCR_TIMEOUT_S,
        )
    except requests.exceptions.RequestException as exc:
        write_log(f"Passport OCR service unreachable: {exc}", source=_LOG_SOURCE, type="error")
        return error_response(503, UNAVAILABLE)

    if resp.status_code == 401:
        # Our server-side key is wrong — never surface that to the browser as the user's fault
        write_log("Passport OCR rejected the API key — check PASSPORT_OCR_API_KEY", source=_LOG_SOURCE, type="error")
        return error_response(503, UNAVAILABLE)

    # Only outcome metadata is logged — never passport data
    write_log(f"Passport scan by {identity}: HTTP {resp.status_code}", source=_LOG_SOURCE, type="info")
    try:
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except ValueError:
        return error_response(502, "Passport scanning returned an invalid response")
