import datetime
import re

from pydantic import BaseModel, Field, root_validator, validator
from typing import List, Optional, Dict, Any

# NOTE: validators are written with `validator` / `root_validator(skip_on_failure=True)` so this
# module works on both pydantic 1.10 (requirements.txt) and pydantic 2.x.

_IATA_RE        = re.compile(r"^[A-Za-z]{3}$")
_AIRLINE_RE     = re.compile(r"^[A-Za-z0-9]{2}$")
_TICKET_RE      = re.compile(r"^\d{13}$")
_PNR_RE         = re.compile(r"^[A-Za-z0-9]{5,8}$")
_TRIP_TYPES     = {"one_way", "round_trip", "multi_city"}
_CABINS         = {"Y", "S", "W", "C", "J", "F", "P", "ALL"}
_PAX_TYPES      = {"ADT", "CNN", "CHD", "INF"}
_MAX_SEATED_PAX = 9
_SUPPLIER_DESC  = "Optional supplier code (e.g. 'SABRE-BD-DAC') or provider key (e.g. 'sabre')"


def _parse_date(value: str, field: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except Exception:
        raise ValueError(f"'{field}' must be a date in YYYY-MM-DD format")


def _iata(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return value
    if not _IATA_RE.match(str(value).strip()):
        raise ValueError(f"'{field}' must be a 3-letter IATA airport/city code")
    return str(value).strip().upper()


def _pnr(value: str) -> str:
    v = str(value or "").strip().upper()
    if not _PNR_RE.match(v):
        raise ValueError("'pnr' must be a 5-8 character alphanumeric record locator")
    return v


def _ticket(value: str, field: str = "ticket_number") -> str:
    v = re.sub(r"[\s-]", "", str(value or ""))
    if not _TICKET_RE.match(v):
        raise ValueError(f"'{field}' must be a 13-digit e-ticket number")
    return v


def _validate_multi_city(segments: Optional[list]) -> None:
    if not segments or len(segments) < 2:
        raise ValueError("multi_city searches require at least 2 segments")
    if len(segments) > 6:
        raise ValueError("multi_city searches support at most 6 segments")
    today, prev = datetime.date.today(), None
    for seg in segments:
        d = _parse_date(seg.departure_date, "segments.departure_date")
        if d < today:
            raise ValueError("segment departure dates cannot be in the past")
        if prev and d < prev:
            raise ValueError("multi_city segments must be in chronological order")
        prev = d


def _validate_point_to_point(values: Dict[str, Any]) -> None:
    for key in ("origin", "destination", "departure_date"):
        if not values.get(key):
            raise ValueError(f"'{key}' is required for one_way/round_trip searches")
    if values["origin"] == values["destination"]:
        raise ValueError("'origin' and 'destination' must differ")
    dep = _parse_date(values["departure_date"], "departure_date")
    if dep < datetime.date.today():
        raise ValueError("'departure_date' cannot be in the past")
    if values.get("trip_type") == "round_trip":
        if not values.get("return_date"):
            raise ValueError("'return_date' is required for round_trip searches")
        if _parse_date(values["return_date"], "return_date") < dep:
            raise ValueError("'return_date' cannot be before 'departure_date'")


def _validate_party(adults: int, children: int, infants: int) -> None:
    if infants > adults:
        raise ValueError("each infant must travel with an adult ('infants' cannot exceed 'adults')")
    if adults + children > _MAX_SEATED_PAX:
        raise ValueError(f"at most {_MAX_SEATED_PAX} seated passengers (adults + children) per booking")


class MultiCitySegment(BaseModel):
    origin: str = Field(..., description="Origin airport IATA code")
    destination: str = Field(..., description="Destination airport IATA code")
    departure_date: str = Field(..., description="Departure date in YYYY-MM-DD format")

    @validator("origin")
    def _check_origin(cls, v):
        return _iata(v, "origin")

    @validator("destination")
    def _check_destination(cls, v):
        return _iata(v, "destination")

    @validator("departure_date")
    def _check_date(cls, v):
        _parse_date(v, "departure_date")
        return v


class FlightSearchRequest(BaseModel):
    # Trip type: one_way | round_trip | multi_city
    trip_type: Optional[str] = Field("one_way", description="Trip type: one_way, round_trip, or multi_city")

    # One-way / Round-trip fields (required unless trip_type is multi_city)
    origin: Optional[str] = Field(None, description="Origin airport code (IATA) — required for one_way/round_trip")
    destination: Optional[str] = Field(None, description="Destination airport code (IATA) — required for one_way/round_trip")
    departure_date: Optional[str] = Field(None, description="Departure date in YYYY-MM-DD format — required for one_way/round_trip")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format (required for round_trip)")

    # Multi-city segments (required when trip_type is multi_city)
    segments: Optional[List[MultiCitySegment]] = Field(None, description="List of flight legs for multi-city searches")

    adults: int = Field(1, ge=1, le=9, description="Number of adult passengers (1-9)")
    children: int = Field(0, ge=0, le=8, description="Number of child passengers")
    infants: int = Field(0, ge=0, le=9, description="Number of lap infants (cannot exceed adults)")
    cabin_class: Optional[str] = Field("Y", description="Cabin class (Y=Economy, S=Premium Economy, C=Business, J=Premium Business, F=First, P=Premium First, ALL)")

    # Advanced BFM Parameters
    direct_flights_only: Optional[bool] = Field(False, description="Set strictly to True to exclude connecting flights.")
    max_stops: Optional[int] = Field(None, ge=0, le=3, description="Maximum number of stops allowed (e.g., 0, 1, 2).")
    included_airlines: Optional[List[str]] = Field(None, description="List of preferred airline IATA codes (e.g., ['BA', 'AA']).")
    excluded_airlines: Optional[List[str]] = Field(None, description="List of airline IATA codes to avoid.")
    flexible_dates: Optional[bool] = Field(False, description="Search +/- 1-3 days around the requested dates for cheaper fares.")
    corporate_code: Optional[str] = Field(None, description="Agency corporate ID or discount code.")
    account_code: Optional[str] = Field(None, description="Negotiated account code for private fares.")
    currency: Optional[str] = Field("BDT", description="Preferred currency code (e.g., USD, EUR, BDT)")

    @validator("trip_type", pre=True, always=True)
    def _check_trip_type(cls, v):
        v = str(v or "one_way").strip().lower().replace("-", "_")
        if v not in _TRIP_TYPES:
            raise ValueError("'trip_type' must be one of one_way, round_trip, multi_city")
        return v

    @validator("origin")
    def _check_origin(cls, v):
        return _iata(v, "origin")

    @validator("destination")
    def _check_destination(cls, v):
        return _iata(v, "destination")

    @validator("cabin_class", pre=True, always=True)
    def _check_cabin(cls, v):
        v = str(v or "Y").strip().upper()
        if v not in _CABINS:
            raise ValueError(f"'cabin_class' must be one of {', '.join(sorted(_CABINS))}")
        return v

    @validator("included_airlines", "excluded_airlines", each_item=True)
    def _check_airline(cls, v):
        if not _AIRLINE_RE.match(str(v).strip()):
            raise ValueError("airline codes must be 2-character IATA codes")
        return str(v).strip().upper()

    @validator("currency")
    def _check_currency(cls, v):
        if v is not None and not re.match(r"^[A-Za-z]{3}$", v):
            raise ValueError("'currency' must be a 3-letter ISO code")
        return v.upper() if v else v

    @root_validator(skip_on_failure=True)
    def validate_trip_fields(cls, values):
        if values.get("trip_type") == "multi_city":
            _validate_multi_city(values.get("segments"))
        else:
            _validate_point_to_point(values)
        _validate_party(values.get("adults", 1), values.get("children", 0), values.get("infants", 0))
        return values

class PricingRequestPassenger(BaseModel):
    passenger_type: str = Field(..., description="Type of passenger (ADT, CNN, INF)")
    quantity: int = Field(..., ge=1, le=9, description="Number of passengers of this type")

    @validator("passenger_type")
    def _check_ptc(cls, v):
        v = str(v).strip().upper()
        if v not in _PAX_TYPES:
            raise ValueError(f"'passenger_type' must be one of {', '.join(sorted(_PAX_TYPES))}")
        return v

class FlightPricingRequest(BaseModel):
    offer_id: Optional[str] = Field(None, description="The unique offer identifier returned from search (required for Travelport)")
    flight_segments: List[Dict[str, Any]] = Field(..., min_items=1, description="List of flight segments from search response")
    passengers: List[PricingRequestPassenger] = Field(..., min_items=1, description="List of passenger counts and types")
    currency: Optional[str] = Field("BDT", description="Currency code for revalidation (e.g., USD, BDT)")
    supplier: Optional[str] = Field(None, description="Supplier code returned in search results (`supplier_code`). Falls back to the segment's `supplier_code`.")

class AtBookingPassenger(BaseModel):
    title: Optional[str] = None
    first_name: str = Field(..., min_length=1, max_length=60)
    last_name: str = Field(..., min_length=1, max_length=60)
    passenger_type: str = Field(..., description="ADT, CNN (or CHD), INF")
    gender: str = Field(..., description="M or F")
    date_of_birth: str = Field(..., description="YYYY-MM-DD")
    email: Optional[str] = None
    phone: Optional[str] = None
    document_number: Optional[str] = None # Passport or ID
    document_expiry: Optional[str] = None # YYYY-MM-DD
    passport_expiry: Optional[str] = None # YYYY-MM-DD (alias of document_expiry, kept for backward compat)
    document_issue_country: Optional[str] = None # Country code
    passport_issue_country: Optional[str] = None # Country code (alias of document_issue_country)
    nationality: Optional[str] = None # Country code

    @validator("passenger_type")
    def _check_ptc(cls, v):
        v = str(v).strip().upper()
        if v not in _PAX_TYPES:
            raise ValueError(f"'passenger_type' must be one of {', '.join(sorted(_PAX_TYPES))}")
        return v

    @validator("gender")
    def _check_gender(cls, v):
        g = str(v).strip().upper()
        if g in ("M", "MALE"):
            return "M"
        if g in ("F", "FEMALE"):
            return "F"
        raise ValueError("'gender' must be M or F")

    @validator("date_of_birth")
    def _check_dob(cls, v):
        if _parse_date(v, "date_of_birth") >= datetime.date.today():
            raise ValueError("'date_of_birth' must be in the past")
        return str(v)[:10]

    @root_validator(skip_on_failure=True)
    def _merge_document_aliases(cls, values):
        values["document_expiry"] = values.get("document_expiry") or values.get("passport_expiry")
        values["document_issue_country"] = values.get("document_issue_country") or values.get("passport_issue_country")
        if values.get("document_number"):
            if not values.get("document_expiry"):
                raise ValueError("'document_expiry' is required when 'document_number' is provided")
            if _parse_date(values["document_expiry"], "document_expiry") <= datetime.date.today():
                raise ValueError("travel document is expired")
        return values

class FlightBookingRequest(BaseModel):
    offer_id: Optional[str] = Field(None, description="The unique offer identifier returned from search (required for Travelport)")
    flight_segments: List[Dict[str, Any]] = Field(..., min_items=1, description="Flight segments to book")
    passengers: List[AtBookingPassenger] = Field(..., min_items=1, description="Passenger details for the booking")
    price_info: Dict[str, Any] = Field(
        ...,
        description=(
            "Price shown to the customer (from /price). Used only to detect a price change — the booking "
            "is always recorded at the price returned by the supplier in the PNR. "
            "Expected keys: total_fare, base_fare, tax_amount, currency."
        )
    )
    validating_carrier: Optional[str] = Field(None, description="Optional airline code to use as validating carrier for pricing")
    supplier: Optional[str] = Field(None, description="Supplier code returned in search results (`supplier_code`). Falls back to the segment's `supplier_code`.")

    @root_validator(skip_on_failure=True)
    def _check_party(cls, values):
        pax = values.get("passengers") or []
        adults = sum(1 for p in pax if p.passenger_type == "ADT")
        infants = sum(1 for p in pax if p.passenger_type == "INF")
        if adults == 0:
            raise ValueError("at least one adult passenger is required")
        if infants > adults:
            raise ValueError("each infant must travel with an adult")
        if len(pax) - infants > _MAX_SEATED_PAX:
            raise ValueError(f"at most {_MAX_SEATED_PAX} seated passengers per booking")
        return values

class TicketingRequest(BaseModel):
    pnr: str = Field(..., description="Passenger Name Record (PNR) locator to ticket")
    confirmed_total: Optional[float] = Field(
        None,
        description=(
            "Total fare the customer confirmed (supplier currency). The fare is re-priced live before "
            "issuing; if it is higher than this amount, ticketing is blocked with HTTP 409 and the new "
            "price. If omitted, the booked fare on record is used as the reference."
        ),
    )
    confirmed_currency: Optional[str] = Field(None, description="Currency of confirmed_total")
    country_code: Optional[str] = Field("BD", description="Two-letter country code for ticketing (default is BD for Bangladesh)")
    printer_id: Optional[str] = Field(None, description="Optional specific printer LNIATA or ID")
    validating_carrier: Optional[str] = Field(None, description="Optional two-letter airline code to use as validating carrier")
    fop_type: Optional[str] = Field("CA", description="Form of payment type (CA=Cash, CK=Check). Card FOP is not supported by this API.")
    commission_percent: Optional[float] = Field(None, description="DEPRECATED — ignored. Commission comes from the supplier configuration.")
    reissue: Optional[bool] = Field(False, description="DEPRECATED — reissues must use /ticket/exchange/quote + /ticket/exchange.")
    quote_number: Optional[int] = Field(None, description="DEPRECATED — ignored. The fare is re-priced and the fresh quote is ticketed.")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)

    @validator("fop_type", pre=True, always=True)
    def _check_fop(cls, v):
        v = str(v or "CA").strip().upper()
        if v not in ("CA", "CK"):
            raise ValueError("'fop_type' must be CA (cash) or CK (check)")
        return v

    @validator("reissue")
    def _no_reissue(cls, v):
        if v:
            raise ValueError("reissue is not allowed here — use /ticket/exchange/quote then /ticket/exchange")
        return v

class RepricePNRRequest(BaseModel):
    pnr: str = Field(..., description="Passenger Name Record (PNR) locator to reprice")
    passenger_types: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Passenger type counts e.g. [{\"Code\": \"ADT\", \"Quantity\": \"1\"}]. Defaults to the passengers on the booking record."
    )
    validating_carrier: Optional[str] = Field(None, description="Optional airline code to force as validating carrier during repricing")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)


class PNRDetailsRequest(BaseModel):
    pnr: str = Field(..., description="Passenger Name Record (PNR) locator to retrieve details for")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)

class CancelItineraryRequest(BaseModel):
    pnr: str = Field(..., description="Passenger Name Record (PNR) locator to cancel")
    cancel_segments: Optional[bool] = Field(True, description="Cancel all flight segments")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)

class VoidTicketRequest(BaseModel):
    ticket_number: str = Field(..., description="The electronic ticket number to void")
    pnr: str = Field(..., description="The associated PNR")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("ticket_number")
    def _check_ticket(cls, v):
        return _ticket(v)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)

class ExchangeQuoteRequest(BaseModel):
    pnr: str = Field(..., description="The PNR containing the ticket to be exchanged")
    original_ticket_number: str = Field(..., description="The ticket number being exchanged")
    new_flight_segments: List[Dict[str, Any]] = Field(..., min_items=1, description="The new flight segments (same shape as search segments)")
    passenger_types: Optional[List[Dict[str, Any]]] = Field(None, description="e.g. [{\"Code\": \"ADT\", \"Quantity\": 1}]. Defaults to the booking record.")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)

    @validator("original_ticket_number")
    def _check_ticket(cls, v):
        return _ticket(v, "original_ticket_number")

class ExchangeTicketRequest(BaseModel):
    pnr: str = Field(..., description="The PNR containing the ticket to be exchanged")
    original_ticket_number: str = Field(..., description="The ticket number being exchanged")
    quote_id: str = Field(..., description="quote_id returned by /ticket/exchange/quote")
    confirmed_amount: float = Field(..., description="Total amount to collect (fare difference + penalties) the customer accepted")
    confirmed_currency: Optional[str] = Field(None, description="Currency of confirmed_amount")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)

    @validator("original_ticket_number")
    def _check_ticket(cls, v):
        return _ticket(v, "original_ticket_number")

class RefundQuoteRequest(BaseModel):
    pnr: str = Field(..., description="The PNR containing the tickets")
    ticket_numbers: List[str] = Field(..., min_items=1, max_items=12, description="13-digit e-ticket numbers to refund")
    waiver_code: Optional[str] = Field(None, description="Airline waiver code, if one was granted")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)

    @validator("ticket_numbers", each_item=True)
    def _check_ticket(cls, v):
        return _ticket(v, "ticket_numbers")

class RefundTicketRequest(RefundQuoteRequest):
    confirmed_refund_amount: float = Field(..., ge=0, description="Refund amount the customer accepted (from /ticket/refund/quote)")
    confirmed_currency: Optional[str] = Field(None, description="Currency of confirmed_refund_amount")
    reason: Optional[str] = Field(None, max_length=255, description="Reason recorded on the refund")

class SeatMapRequest(BaseModel):
    pnr: Optional[str] = Field(None, description="Optional. When given, the seat map is fetched from the supplier that made this booking.")
    flight_segment: Dict[str, Any] = Field(
        ...,
        description="One segment exactly as returned by /search (carrier, flight number, origin, destination, "
                    "departure and arrival date/time, bookingCode)."
    )
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

class BaggageAllowanceRequest(BaseModel):
    pnr: str = Field(..., description="PNR locator")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)

class QueueRequest(BaseModel):
    pnr: str = Field(..., description="PNR locator")
    pseudo_city_code: str = Field(..., description="Agency PCC")
    queue_number: str = Field(..., description="Queue number to place the PNR on")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v)

class FareRulesRequest(BaseModel):
    """
    Either `pnr` (booked fare, every supplier) or a search result (`offer_id` / `flight_segment`,
    Travelport only — Sabre exposes fare rules over REST for booked PNRs only).
    """
    pnr: Optional[str] = Field(None, description="PNR locator: rules of the booked fare")
    offer_id: Optional[str] = Field(None, description="Offer `id` from /search (Travelport): rules before booking")
    flight_segment: Optional[Dict[str, Any]] = Field(
        None, description="A segment from /search; its `offer_id`/`id` and `supplier_code` are used when the fields above are empty"
    )
    include_text: bool = Field(False, description="Also return the airline's rule text per category (Travelport)")
    supplier: Optional[str] = Field(None, description=_SUPPLIER_DESC)

    @validator("pnr")
    def _check_pnr(cls, v):
        return _pnr(v) if v else v

    @root_validator(skip_on_failure=True)
    def _need_booking_or_offer(cls, values):
        if not (values.get("pnr") or values.get("offer_id") or values.get("flight_segment")):
            raise ValueError("send 'pnr' for a booked fare, or 'offer_id' / 'flight_segment' from /search")
        return values

    @property
    def search_offer_id(self) -> Optional[str]:
        segment = self.flight_segment or {}
        return self.offer_id or segment.get("offer_id") or segment.get("offerId") or segment.get("id")
