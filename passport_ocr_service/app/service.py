import datetime
from typing import Dict, List, Optional, Tuple

from app.countries import country_name, icao_to_iso2
from app.mrz_parser import MRZResult
from app.ocr import looks_like_filler
from app.schemas import BookingPassenger, FieldValue, MRZLines, PassportData, PassportOCRResponse, VisualZone
from app.viz import VizResult, fits_validity

_FIELD_LABELS = {
    "document_number": "document_number",
    "date_of_birth": "date_of_birth",
    "expiry_date": "expiry_date",
    "personal_number": "personal_number",
}
# Fields that decide the booking — overall_confidence is the weakest of these
_BOOKING_FIELDS = ("surname", "given_names", "gender", "date_of_birth", "document_number",
                   "expiry_date", "nationality", "issuing_country")
_CONFIRMED = 0.95  # a name at or above this was read identically from the MRZ and the printed page


def _iso(d: Optional[datetime.date]) -> Optional[str]:
    return d.isoformat() if d else None


def _passenger_type(dob: Optional[datetime.date]) -> Optional[str]:
    if not dob:
        return None
    today = datetime.date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 2:
        return "INF"
    return "CNN" if age < 12 else "ADT"


def _viz_value(viz: Optional[VizResult], name: str) -> Tuple[Optional[str], float]:
    f = viz.fields.get(name) if viz else None
    return (f.value, f.confidence) if f else (None, 0.0)


def _reconcile_name(mrz_value: str, viz: Optional[VizResult], caption: str, fallback: Optional[str]) -> Tuple[str, float, Optional[str]]:
    """
    Names have no check digit, so the MRZ reading is compared with the printed page.
    Returns (name, confidence, warning). Misread-filler tokens (CCCC, KKK, EERERE) are dropped.
    """
    words = viz.words if viz else set()
    tokens = mrz_value.split()
    garbage = [t for t in tokens if looks_like_filler(t) and t not in words]
    clean = " ".join(t for t in tokens if t not in garbage)
    printed, printed_conf = _viz_value(viz, caption)
    printed = printed or fallback

    if printed:
        if printed == clean:
            return clean, 0.98, None
        if garbage or not clean:
            # MRZ name was damaged: the printed name, if it starts the same way, is the better reading
            if not clean or printed.startswith(clean.split()[0]):
                return printed, round(min(0.92, max(printed_conf, 0.8)), 2), None
        if printed.startswith(clean) and len(printed) > len(clean):
            return printed, 0.9, None  # MRZ truncates long names; the printed page has them in full
    if clean and viz and all(t in words for t in clean.split()):
        return clean, 0.96, None
    if clean:
        warning = None
        if printed and printed != clean:
            warning = f"Name on the printed page ('{printed}') differs from the MRZ ('{clean}') — please confirm"
        return clean, (0.6 if garbage or warning else 0.8), warning
    return mrz_value, 0.3, "Name could not be read reliably — please type it"


def _holder_name_parts(viz: Optional[VizResult], surname: str) -> Optional[str]:
    """Given names from the personal-data page's full name ('MD SAIFUL ISLAM' minus the surname)."""
    full, _ = _viz_value(viz, "full_name")
    if full and surname and full.endswith(" " + surname):
        return full[: -len(surname) - 1].strip()
    if full and surname and full.startswith(surname + " "):
        return full[len(surname) + 1:].strip()
    return None


def _issue_date(viz: Optional[VizResult], expiry: Optional[datetime.date]) -> Optional[FieldValue]:
    """Printed issue date, cross-checked against the validity period (passports run 5 or 10 years)."""
    value, conf = _viz_value(viz, "date_of_issue")
    if not value:
        return None
    if expiry and fits_validity(datetime.date.fromisoformat(value), expiry):
        conf = max(conf, 0.96)
    else:
        conf = min(conf, 0.7)
    return FieldValue(value=value, confidence=round(conf, 2))


def _visual_zone(viz: Optional[VizResult], expiry, holder_name: str) -> Optional[VisualZone]:
    if viz is None:
        return None
    out = {}
    for name in VisualZone.model_fields:
        if name == "date_of_issue":
            out[name] = _issue_date(viz, expiry)
            continue
        value, conf = _viz_value(viz, name)
        if value:
            if name == "full_name" and value == holder_name:
                conf = 0.99  # same as the MRZ names
            out[name] = FieldValue(value=value, confidence=conf)
    return VisualZone(**out)


def build_response(mrz: MRZResult, processing_ms: int, viz: Optional[VizResult] = None) -> PassportOCRResponse:
    """The full response; the endpoint returns only the sections the caller asked for."""
    warnings = list(mrz.warnings)
    today = datetime.date.today()
    if mrz.expiry_date:
        if mrz.expiry_date < today:
            warnings.append("Passport has expired")
        elif mrz.expiry_date < today + datetime.timedelta(days=183):
            warnings.append("Passport expires within 6 months — many countries refuse entry")
    if not mrz.checks.get("composite", True):
        warnings.append("Composite check digit failed — at least one field may be misread")

    surname, surname_conf, w1 = _reconcile_name(mrz.surname, viz, "surname", None)
    given, given_conf, w2 = _reconcile_name(mrz.given_names, viz, "given_names", _holder_name_parts(viz, surname))
    full, _ = _viz_value(viz, "full_name")
    if full and full == f"{given} {surname}":
        surname_conf = given_conf = 0.99  # personal-data page agrees with both
    warnings += [w for w in (w1, w2) if w]

    corrected = any("confirmed against the printed passport page" in w for w in mrz.warnings)
    check_conf = lambda key: (0.97 if corrected and key == "document_number" else 0.99) if mrz.checks.get(key) else 0.3
    issuing_iso2 = icao_to_iso2(mrz.issuing_country)
    nationality_iso2 = icao_to_iso2(mrz.nationality)
    confidence: Dict[str, float] = {
        "surname": surname_conf,
        "given_names": given_conf,
        "document_number": check_conf("document_number"),
        "date_of_birth": check_conf("date_of_birth"),
        "expiry_date": check_conf("expiry_date"),
        "personal_number": check_conf("personal_number") if mrz.personal_number else 1.0,
        # Not covered by a check digit: plausible values only
        "gender": 0.95 if mrz.sex in ("M", "F", "X") else 0.3,
        "nationality": 0.97 if nationality_iso2 else 0.4,
        "issuing_country": 0.97 if issuing_iso2 else 0.4,
    }
    overall = round(min(confidence[k] for k in _BOOKING_FIELDS), 2)

    unverified: List[str] = [_FIELD_LABELS[k] for k, ok in mrz.checks.items() if not ok and k in _FIELD_LABELS]
    unverified += [k for k in ("surname", "given_names") if confidence[k] < _CONFIRMED]

    data = PassportData(
        mrz_format=mrz.format,
        document_type=mrz.document_type,
        document_number=mrz.document_number,
        issuing_country=mrz.issuing_country,
        issuing_country_iso2=issuing_iso2,
        issuing_country_name=country_name(mrz.issuing_country),
        surname=surname,
        given_names=given,
        nationality=mrz.nationality,
        nationality_iso2=nationality_iso2,
        date_of_birth=_iso(mrz.date_of_birth),
        gender=mrz.sex,
        expiry_date=_iso(mrz.expiry_date),
        personal_number=mrz.personal_number or None,
    )
    passenger = BookingPassenger(
        first_name=given,
        last_name=surname,
        gender=mrz.sex,
        date_of_birth=data.date_of_birth,
        passenger_type=_passenger_type(mrz.date_of_birth),
        document_number=mrz.document_number,
        document_expiry=data.expiry_date,
        document_issue_country=issuing_iso2,
        nationality=nationality_iso2,
    )
    return PassportOCRResponse(
        status="success" if mrz.valid else "partial",
        message="Passport read and verified" if mrz.valid else "Passport read, but some fields could not be verified — please review",
        data=data,
        booking_passenger=passenger,
        confidence=confidence,
        overall_confidence=overall,
        visual_zone=_visual_zone(viz, mrz.expiry_date, f"{given} {surname}"),
        checks=mrz.checks,
        unverified_fields=unverified,
        warnings=warnings,
        mrz=MRZLines(format=mrz.format, lines=mrz.lines),
        processing_ms=processing_ms,
    )
