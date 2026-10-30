from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PassportData(BaseModel):
    mrz_format: str = Field(..., description="TD3 (passport book), TD2 or TD1 (passport card)")
    document_type: str = Field(..., description="'P' for passports (second letter is the issuer's sub-type, if any)")
    document_number: str
    issuing_country: str = Field(..., description="ICAO 3-letter code, e.g. BGD")
    issuing_country_iso2: Optional[str] = Field(None, description="ISO 3166 alpha-2, e.g. BD")
    issuing_country_name: Optional[str] = None
    surname: str
    given_names: str
    nationality: str = Field(..., description="ICAO 3-letter code")
    nationality_iso2: Optional[str] = None
    date_of_birth: Optional[str] = Field(None, description="YYYY-MM-DD")
    gender: str = Field(..., description="M, F or X (unspecified)")
    expiry_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    personal_number: Optional[str] = None


class BookingPassenger(BaseModel):
    """Same field names as the OTA /flights/book passenger, ready to prefill the booking form."""
    first_name: str
    last_name: str
    gender: str
    date_of_birth: Optional[str]
    passenger_type: Optional[str] = Field(None, description="ADT / CNN / INF by age today — re-check against the travel date")
    document_number: str
    document_expiry: Optional[str]
    document_issue_country: Optional[str]
    nationality: Optional[str]


class FieldValue(BaseModel):
    value: str
    confidence: float = Field(..., description="0–1: how sure the reading is")


class VisualZone(BaseModel):
    """Printed-only fields (not in the MRZ). Present only when the page shows them and they could be read."""
    full_name: Optional[FieldValue] = None
    place_of_birth: Optional[FieldValue] = None
    date_of_issue: Optional[FieldValue] = Field(None, description="YYYY-MM-DD")
    issuing_authority: Optional[FieldValue] = None
    previous_passport_number: Optional[FieldValue] = None
    father_name: Optional[FieldValue] = None
    mother_name: Optional[FieldValue] = None
    spouse_name: Optional[FieldValue] = None
    legal_guardian_name: Optional[FieldValue] = None
    permanent_address: Optional[FieldValue] = None
    present_address: Optional[FieldValue] = None
    address: Optional[FieldValue] = None
    telephone: Optional[FieldValue] = None
    emergency_contact_name: Optional[FieldValue] = None
    emergency_contact_relationship: Optional[FieldValue] = None
    emergency_contact_address: Optional[FieldValue] = None
    emergency_contact_telephone: Optional[FieldValue] = None


class MRZLines(BaseModel):
    format: str
    lines: List[str]


class PassportOCRResponse(BaseModel):
    status: str = Field(..., description="success (all check digits valid) | partial (some fields could not be verified)")
    message: str
    data: PassportData
    # Optional sections: present only when requested with include_<section>=true (or include_all=true)
    booking_passenger: Optional[BookingPassenger] = Field(None, description="include_booking_passenger")
    confidence: Optional[Dict[str, float]] = Field(None, description="include_confidence: 0–1 per field of `data`")
    overall_confidence: Optional[float] = Field(None, description="include_confidence: weakest booking-critical field")
    visual_zone: Optional[VisualZone] = Field(None, description="include_visual_zone: printed-only fields that could be read")
    checks: Optional[Dict[str, bool]] = Field(None, description="include_checks: ICAO check-digit result per field")
    unverified_fields: Optional[List[str]] = Field(None, description="include_checks: failed check digits, and names not confirmed by the printed page")
    warnings: Optional[List[str]] = Field(None, description="include_warnings")
    mrz: Optional[MRZLines] = Field(None, description="include_mrz: the raw MRZ lines")
    processing_ms: int


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
    hints: List[str] = Field(default_factory=list)
