"""
Passport scanning for the booking form.

The frontend calls this endpoint with the user's normal Bearer token (AuthMiddleware). The upload is
forwarded to the internal passport_ocr microservice by app/helpers/passport.py.
"""

from fastapi import APIRouter, File, Query, Request, UploadFile

from app.helpers import passport
from app.utils.request_utils import get_client_ip, get_optional_user_id

router = APIRouter()


@router.post(
    "/ocr",
    summary="Scan Passport",
    description=(
        "Upload a photo or scan of the passport data page (JPEG, PNG, WEBP, TIFF, HEIC or PDF, max 10 MB). "
        "Returns `data` (passport fields verified against the MRZ check digits). Every other section is opt-in "
        "with its include_* flag: booking_passenger, confidence, visual_zone (address, phone, parents, issue date …), "
        "checks, warnings, mrz — or include_all. Nothing is stored."
    ),
)
def scan_passport(
    http_request: Request,
    file: UploadFile = File(...),
    include_all: bool = Query(False, description="Every section below"),
    include_booking_passenger: bool = Query(False, description="`booking_passenger`: ready for /flights/book"),
    include_confidence: bool = Query(False, description="`confidence` per field + `overall_confidence` (+2–4 s)"),
    include_visual_zone: bool = Query(False, description="`visual_zone`: address, phone, parents, issue date … (+2–4 s)"),
    include_checks: bool = Query(False, description="`checks` + `unverified_fields`"),
    include_warnings: bool = Query(False, description="`warnings`: expired / expiring passport …"),
    include_mrz: bool = Query(False, description="`mrz`: raw machine-readable lines"),
):
    identity = get_optional_user_id(http_request) or get_client_ip(http_request)
    sections = {
        "include_all": include_all, "include_booking_passenger": include_booking_passenger,
        "include_confidence": include_confidence, "include_visual_zone": include_visual_zone,
        "include_checks": include_checks, "include_warnings": include_warnings, "include_mrz": include_mrz,
    }
    return passport.scan_passport(file, str(identity), sections)
