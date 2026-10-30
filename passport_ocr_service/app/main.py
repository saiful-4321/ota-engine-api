"""
Passport OCR microservice.

Reads the machine-readable zone (MRZ) of a passport photo / scan and returns the verified fields.
Images are processed in memory only — never written to disk or logged.
"""

import base64
import binascii
import logging
import os
import secrets
import time
from typing import Optional, Set

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.image_io import UnsupportedFile, load_images
from app.ocr import looks_like_filler, read_passport
from app.viz import read_visual_zone
from app.schemas import ErrorResponse, PassportOCRResponse
from app.service import build_response

API_KEY = os.getenv("API_KEY", "")
ALLOW_NO_AUTH = os.getenv("ALLOW_NO_AUTH", "false").lower() == "true"
MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "10"))
OCR_TIMEOUT_S = int(os.getenv("OCR_TIMEOUT_S", "20"))
DOCS_ENABLED = os.getenv("DOCS_ENABLED", "true").lower() == "true"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("passport_ocr")

if not API_KEY and not ALLOW_NO_AUTH:
    # Passport data is sensitive — refuse to run open unless explicitly allowed (local dev only)
    raise RuntimeError("API_KEY is not set. Set API_KEY, or ALLOW_NO_AUTH=true for local development only.")

app = FastAPI(
    title="Passport OCR Service",
    version="1.1.0",
    description="Extracts and verifies passport data from the MRZ (ICAO 9303 TD3 / TD2 / TD1) and the printed pages.",
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url=None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)

_UNREADABLE_HINTS = [
    "Photograph the full passport data page, including the two lines of <<< characters at the bottom",
    "Avoid glare, shadows and blur; place the passport on a dark, flat surface",
    "Use a resolution of at least 1000 px across the data page",
]


# Response sections beyond `data`, each switched on by its own include_<section> flag
_SECTIONS = {
    "booking_passenger": ("booking_passenger",),
    "confidence": ("confidence", "overall_confidence"),
    "visual_zone": ("visual_zone",),
    "checks": ("checks", "unverified_fields"),
    "warnings": ("warnings",),
    "mrz": ("mrz",),
}
_ALWAYS = ("status", "message", "data", "processing_ms")


def _selected(include_all: bool, flags: dict) -> Set[str]:
    return set(_SECTIONS) if include_all else {name for name, on in flags.items() if on}


def include_params(
    include_all: bool = Query(False, description="Every section below"),
    include_booking_passenger: bool = Query(False, description="`booking_passenger`: fields named like the /flights/book passenger"),
    include_confidence: bool = Query(False, description="`confidence` per field + `overall_confidence` (reads the printed page: +2–4 s)"),
    include_visual_zone: bool = Query(False, description="`visual_zone`: printed-only fields — address, phone, parents, issue date … (+2–4 s)"),
    include_checks: bool = Query(False, description="`checks` (check digit per field) + `unverified_fields`"),
    include_warnings: bool = Query(False, description="`warnings`: expired / expiring passport, non-passport document …"),
    include_mrz: bool = Query(False, description="`mrz`: the raw machine-readable lines (support/debugging)"),
) -> Set[str]:
    return _selected(include_all, {
        "booking_passenger": include_booking_passenger, "confidence": include_confidence,
        "visual_zone": include_visual_zone, "checks": include_checks,
        "warnings": include_warnings, "mrz": include_mrz,
    })


class Base64Request(BaseModel):
    image_base64: str = Field(..., description="Base64 image or PDF; a data: URL prefix is accepted")
    include_all: bool = False
    include_booking_passenger: bool = False
    include_confidence: bool = False
    include_visual_zone: bool = False
    include_checks: bool = False
    include_warnings: bool = False
    include_mrz: bool = False

    def sections(self) -> Set[str]:
        return _selected(self.include_all, {name: getattr(self, f"include_{name}") for name in _SECTIONS})


def _error(status: int, message: str, hints=None) -> JSONResponse:
    return JSONResponse(status_code=status, content=ErrorResponse(message=message, hints=hints or []).model_dump())


def require_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    if API_KEY and not secrets.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@app.exception_handler(HTTPException)
def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return _error(exc.status_code, str(exc.detail))


def _name_damaged(mrz) -> bool:
    tokens = (mrz.surname + " " + mrz.given_names).split()
    return not mrz.given_names or any(looks_like_filler(t) for t in tokens)


def _process(data: bytes, sections: Set[str]):
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        return _error(413, f"File too large (max {MAX_UPLOAD_MB:g} MB)")
    started = time.monotonic()
    try:
        images = load_images(data)
    except UnsupportedFile as exc:
        return _error(415, str(exc))

    wants_page = bool(sections & {"visual_zone", "confidence"})
    mrz, page = read_passport(images, timeout_s=OCR_TIMEOUT_S, prefetch_page=wants_page)
    if mrz is None:
        elapsed = int((time.monotonic() - started) * 1000)
        logger.info("passport ocr: no MRZ found (%d ms)", elapsed)
        return _error(422, "No passport MRZ could be read from the image", _UNREADABLE_HINTS)
    # The printed page costs 2–4 s: read it when asked for, or to repair a damaged MRZ name in `data`
    viz = None
    if page is not None and (wants_page or _name_damaged(mrz)):
        viz = read_visual_zone(page, dob=mrz.date_of_birth, expiry=mrz.expiry_date)
    elapsed = int((time.monotonic() - started) * 1000)

    # Log only outcome metadata — never passport data
    logger.info("passport ocr: format=%s status=%s checks=%d/%d (%d ms)", mrz.format,
                "valid" if mrz.valid else "partial", sum(mrz.checks.values()), len(mrz.checks), elapsed)
    full = build_response(mrz, elapsed, viz).model_dump()
    keys = set(_ALWAYS).union(*(_SECTIONS[name] for name in sections))
    body = {k: v for k, v in full.items() if k in keys}
    if body.get("visual_zone"):
        body["visual_zone"] = {k: v for k, v in body["visual_zone"].items() if v is not None}  # read fields only
    return JSONResponse(content=body)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/v1/passport/ocr",
    response_model=PassportOCRResponse,
    responses={401: {"model": ErrorResponse}, 413: {"model": ErrorResponse},
               415: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    dependencies=[Depends(require_api_key)],
    summary="Read a passport from an uploaded image or PDF",
)
def ocr_upload(
    file: UploadFile = File(..., description="JPEG, PNG, WEBP, TIFF, HEIC or PDF of the passport data page"),
    sections: Set[str] = Depends(include_params),
):
    """Returns `status`, `message`, `data` and `processing_ms`; every other section is opt-in via its include_* flag."""
    return _process(file.file.read(int(MAX_UPLOAD_MB * 1024 * 1024) + 1), sections)


@app.post(
    "/v1/passport/ocr/base64",
    response_model=PassportOCRResponse,
    responses={401: {"model": ErrorResponse}, 413: {"model": ErrorResponse},
               415: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    dependencies=[Depends(require_api_key)],
    summary="Read a passport from a base64-encoded image or PDF",
)
def ocr_base64(body: Base64Request):
    payload = body.image_base64.split(",", 1)[1] if body.image_base64.startswith("data:") else body.image_base64
    try:
        data = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError):
        return _error(415, "image_base64 is not valid base64")
    return _process(data, body.sections())
