import uuid
import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy import text

from app.models.sabre_schemas import FlightSearchRequest, FlightBookingRequest, TicketingRequest
from app.models.otadb.SearchRequest import SearchRequest
from app.models.otadb.AtBooking import AtBooking
from app.models.otadb.AtBookingJourney import AtBookingJourney
from app.models.otadb.AtBookingSegment import AtBookingSegment
from app.models.otadb.AtBookingPassenger import AtBookingPassenger
from app.models.otadb.AtFlightTicket import AtFlightTicket
from app.models.otadb.AtTicketCoupon import AtTicketCoupon
from app.models.otadb.Supplier import Supplier
from app.models.otadb.SupplierTransaction import SupplierTransaction
from app.models.otadb.AtPricingSnapshot import AtPricingSnapshot
from app.models.otadb.AtPricingComponent import AtPricingComponent
from app.models.otadb.Payment import Payment
from app.models.otadb.AtRefund import AtRefund
from app.models.otadb.AtBookingStatusHistory import AtBookingStatusHistory
from app.models.otadb.AtAuditEvent import AtAuditEvent
from app.helpers.common import get_ota_db_session, write_log
from app.utils.currency import convert_to_bdt, normalize_rate, DEFAULT_CURRENCY
from app.helpers.flight.registry import resolve_supplier


# ═══════════════════════════════════════════════════════════════════════════
# Helper: Parse datetimes / dates
# ═══════════════════════════════════════════════════════════════════════════

def _parse_dt(dt_str: Any) -> datetime.datetime:
    """Helper to parse datetime strings safely."""
    if not dt_str or not isinstance(dt_str, str):
        return datetime.datetime.utcnow()
    try:
        clean = dt_str.replace('Z', '').replace('T', ' ')
        return datetime.datetime.fromisoformat(clean)
    except Exception:
        return datetime.datetime.utcnow()

def _parse_date(d_str: Any) -> Optional[datetime.date]:
    """Helper to parse date strings safely."""
    if not d_str or not isinstance(d_str, str):
        return None
    try:
        return datetime.date.fromisoformat(d_str)
    except Exception:
        return None

def _parse_duration(dur_val: Any) -> Optional[int]:
    """Parses various duration formats (e.g., '5h 10m', '05:10', 310) into total minutes."""
    if dur_val is None:
        return None
    if isinstance(dur_val, (int, float)):
        return int(dur_val)
    dur_str = str(dur_val).strip().lower()
    if dur_str.isdigit():
        return int(dur_str)
    
    minutes = 0
    # Handle "5h 10m" or "5h" or "10m"
    if 'h' in dur_str or 'm' in dur_str:
        parts = dur_str.replace('h', 'h ').replace('m', 'm ').split()
        for p in parts:
            if 'h' in p:
                minutes += int(p.replace('h', '').strip()) * 60
            elif 'm' in p:
                minutes += int(p.replace('m', '').strip())
        return minutes if minutes > 0 else None
        
    # Handle "05:10"
    if ':' in dur_str:
        parts = dur_str.split(':')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]) * 60 + int(parts[1])
            
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Helper: Extract amounts from price_info (handles all key variants)
# ═══════════════════════════════════════════════════════════════════════════

def _extract_price_info(pi: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts and normalises all pricing fields from the price_info dict.

    Handles key variants from:
      • Search response   (format_bfm_response)  → baseFare, taxes, numericPrice
      • Pricing response  (format_pricing_response) → base, taxes, total
      • Direct client     (manually built)        → base_fare, tax_amount, total_fare
    """
    raw_total = (
        pi.get("total_fare") or pi.get("totalFare") or pi.get("total_amount")
        or pi.get("total_price") or pi.get("total") or pi.get("numericPrice") or 0
    )
    raw_base = (
        pi.get("base_fare") or pi.get("baseFare")
        or pi.get("base") or pi.get("base_price") or 0
    )
    raw_taxes_list = pi.get("taxes") or pi.get("tax_breakdown") or pi.get("taxBreakdown")
    raw_tax_val = pi.get("tax_amount") or pi.get("taxAmount") or 0

    tax_breakdown = []
    if isinstance(raw_taxes_list, list) and len(raw_taxes_list) > 0:
        tax_sum = 0
        for t in raw_taxes_list:
            t_amt = t.get("amount") or t.get("Amount") or 0
            t_code = t.get("code") or t.get("TaxCode") or "TAX"
            tax_sum += float(t_amt)
            tax_breakdown.append({"code": t_code, "amount": float(t_amt)})
        raw_tax = tax_sum
    else:
        raw_tax = float(raw_tax_val or raw_taxes_list or 0)

    raw_service = pi.get("service_fee") or pi.get("serviceFee") or 0
    raw_discount = pi.get("discount_amount") or pi.get("discountAmount") or 0
    raw_commission = pi.get("commission") or pi.get("commission_amount") or 0

    # Derive total if missing
    if not raw_total and (raw_base or raw_tax):
        raw_total = float(raw_base or 0) + float(raw_tax or 0) + float(raw_service or 0)

    # If only total but no breakdown, attribute to base
    if raw_total and not raw_base and not raw_tax:
        raw_base = raw_total

    return {
        "total": raw_total,
        "base": raw_base,
        "tax": raw_tax,
        "tax_breakdown": tax_breakdown,
        "service_fee": raw_service,
        "discount": raw_discount,
        "commission": raw_commission,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Helper: Get exchange rate from DB
# ═══════════════════════════════════════════════════════════════════════════

def _get_conversion_rate(db, search_currency: str) -> Decimal:
    """Fetch the conversion rate from the currencies table."""
    if search_currency == "BDT":
        return Decimal("1.000000")
    try:
        result = db.execute(
            text("SELECT exchange_rate FROM currencies WHERE code = :code AND status = 'Active'"),
            {"code": search_currency}
        ).fetchone()
        if result and result[0]:
            return normalize_rate(float(result[0]), search_currency)
    except Exception as e:
        write_log(f"Failed to fetch exchange rate for {search_currency}: {e}",
                  source="flight.logger._get_conversion_rate", type="warning")
    return Decimal("1.000000")


# ═══════════════════════════════════════════════════════════════════════════
# Helper: Segment field extraction (handles all supplier response formats)
# ═══════════════════════════════════════════════════════════════════════════

def _extract_segment_fields(seg: Dict[str, Any], index: int) -> Dict[str, Any]:
    """
    Parse a segment dict from the booking request into normalised fields.
    Handles both camelCase (Sabre) and snake_case (normalised) keys.
    """
    # Departure datetime

    # Departure datetime
    dep_val = seg.get("departure") or seg.get("DepartureDateTime")
    dep_str = ""
    if isinstance(dep_val, dict):
        dep_str = f"{dep_val.get('date', '')}T{dep_val.get('time', '')}"
    elif isinstance(dep_val, str):
        dep_str = dep_val

    # Arrival datetime
    arr_val = seg.get("arrival") or seg.get("ArrivalDateTime")
    arr_str = ""
    if isinstance(arr_val, dict):
        arr_str = f"{arr_val.get('date', '')}T{arr_val.get('time', '')}"
    elif isinstance(arr_val, str):
        arr_str = arr_val

    # Marketing airline code — prefer direct snake_case fields first
    air_code = seg.get("carrier_code") or seg.get("marketing_carrier") or "XX"
    air_val = seg.get("airline") or seg.get("MarketingAirline")
    if isinstance(air_val, dict):
        air_code = air_val.get("code") or air_val.get("Code") or air_val.get("marketing") or air_code
    elif isinstance(air_val, str) and air_val:
        air_code = air_val

    # Operating carrier
    op_val = seg.get("operating_carrier") or seg.get("OperatingAirline") or seg.get("operatingCarrier")
    op_code = None
    if isinstance(op_val, dict):
        op_code = op_val.get("code") or op_val.get("Code")
    elif isinstance(op_val, str) and op_val:
        op_code = op_val

    # Origin — prefer direct snake_case; also extract terminal from OriginLocation dict
    orig_code = seg.get("origin", "")
    term_dep = seg.get("terminal_departure")
    orig_val = seg.get("OriginLocation") or (seg.get("origin") if isinstance(seg.get("origin"), dict) else None)
    if not orig_val and isinstance(seg.get("departure"), dict):
        orig_val = seg.get("departure")
        
    if isinstance(orig_val, dict):
        orig_code = orig_val.get("LocationCode") or orig_val.get("code") or orig_val.get("airport") or orig_code
        term_dep = term_dep or orig_val.get("Terminal") or orig_val.get("terminal")
    elif not orig_code:
        raw = seg.get("origin") or seg.get("departure")
        if isinstance(raw, str):
            orig_code = raw

    # Destination — prefer direct snake_case; also extract terminal from DestinationLocation dict
    dest_code = seg.get("destination", "")
    term_arr = seg.get("terminal_arrival")
    dest_val = seg.get("DestinationLocation") or (seg.get("destination") if isinstance(seg.get("destination"), dict) else None)
    if not dest_val and isinstance(seg.get("arrival"), dict):
        dest_val = seg.get("arrival")
        
    if isinstance(dest_val, dict):
        dest_code = dest_val.get("LocationCode") or dest_val.get("code") or dest_val.get("airport") or dest_code
        term_arr = term_arr or dest_val.get("Terminal") or dest_val.get("terminal")
    elif not dest_code:
        raw = seg.get("destination") or seg.get("arrival")
        if isinstance(raw, str):
            dest_code = raw

    # Cabin / booking class
    cabin = (seg.get("cabin_class") or seg.get("ResBookDesigCode")
             or seg.get("bookingClass") or seg.get("bookingCode")
             or seg.get("CabinCode") or seg.get("Cabin") or seg.get("cabinClass") or "Y")
    if isinstance(cabin, dict):
        cabin = cabin.get("code") or "Y"

    booking_class = (seg.get("booking_class") or seg.get("ResBookDesigCode")
                     or seg.get("BookingCode") or seg.get("bookingClass") or None)

    raw_duration = seg.get("duration_minutes") or seg.get("ElapsedTime") or seg.get("duration") or None

    equip = seg.get("Equipment") or {}
    aircraft = (seg.get("aircraft_code") or seg.get("aircraftCode")
                or equip.get("AirEquipType") or equip.get("AircraftCode") or None)

    offered = seg.get("OfferedBaggage") or [{}]
    offered_bag = offered[0] if (isinstance(offered, list) and offered) else {}
    baggage_allow = (seg.get("baggage_allowance") or seg.get("baggage")
                     or seg.get("BaggageAllowance") or offered_bag.get("BaggageAllowance") or None)

    return {
        "segment_number": index + 1,
        "carrier_code": str(air_code)[:3].upper(),
        "marketing_carrier": str(air_code)[:3].upper(),
        "operating_carrier": str(op_code)[:3].upper() if op_code else None,
        "flight_number": str(seg.get("flight_number") or seg.get("flightNumber") or seg.get("FlightNumber") or ""),
        "origin": str(orig_code)[:3].upper() if orig_code else "",
        "destination": str(dest_code)[:3].upper() if dest_code else "",
        "departure_at": _parse_dt(dep_str),
        "arrival_at": _parse_dt(arr_str),
        "cabin_class": str(cabin)[:20].upper(),
        "booking_class": str(booking_class)[:10].upper() if booking_class else None,
        "fare_basis": seg.get("fare_basis") or seg.get("fareBasis") or seg.get("FareBasis") or seg.get("FareBasisCode") or None,
        "aircraft_code": aircraft,
        "stop_quantity": seg.get("stop_quantity") or seg.get("stopQuantity") or 0,
        "duration_minutes": _parse_duration(raw_duration),
        "duration_raw": raw_duration,
        "baggage_allowance": baggage_allow,
        "baggage_info": seg.get("baggage_info") or None,
        "terminal_departure": str(term_dep)[:10] if term_dep else None,
        "terminal_arrival": str(term_arr)[:10] if term_arr else None,
    }


def _get_location_names(db: Any, iata: str) -> tuple:
    """Returns (airport_name, city_name) from DB for a given IATA code."""
    if not iata:
        return None, None
    try:
        res = db.execute(text(
            "SELECT a.name AS airport_name, c.name AS city_name "
            "FROM airports a LEFT JOIN cities c ON a.city_id = c.id "
            "WHERE a.iata_code = :iata LIMIT 1"
        ), {"iata": iata}).fetchone()
        if res:
            return res[0], res[1]
    except Exception:
        pass
    return None, None


# ═══════════════════════════════════════════════════════════════════════════
# Helper: Group segments into journeys
# ═══════════════════════════════════════════════════════════════════════════

def _build_journeys(segments: List[Dict[str, Any]], trip_type: Optional[str] = None) -> List[Dict]:
    """
    Groups segments into journeys based on the trip type.

    Strategy:
      - ONE_WAY:     all segments → 1 journey
      - ROUND_TRIP:  split by midpoint (half outbound, half inbound)
      - MULTI_CITY:  each segment with a unique O&D pair forms a journey
      - Fallback:    treat all as 1 journey
    """
    if not segments:
        return []

    parsed = [_extract_segment_fields(s, i) for i, s in enumerate(segments)]
    trip = (trip_type or "one_way").lower().replace("-", "_")

    if trip == "round_trip" and len(parsed) >= 2:
        # Split at midpoint
        mid = len(parsed) // 2
        outbound_segs = parsed[:mid]
        inbound_segs = parsed[mid:]
        return [
            {
                "direction": "OUTBOUND",
                "origin": outbound_segs[0]["origin"],
                "destination": outbound_segs[-1]["destination"],
                "departure_date": outbound_segs[0]["departure_at"].date() if outbound_segs[0]["departure_at"] else datetime.date.today(),
                "segments": outbound_segs,
            },
            {
                "direction": "INBOUND",
                "origin": inbound_segs[0]["origin"],
                "destination": inbound_segs[-1]["destination"],
                "departure_date": inbound_segs[0]["departure_at"].date() if inbound_segs[0]["departure_at"] else datetime.date.today(),
                "segments": inbound_segs,
            },
        ]

    # ONE_WAY, MULTI_CITY, or fallback: 1 journey per direction
    return [
        {
            "direction": None,
            "origin": parsed[0]["origin"],
            "destination": parsed[-1]["destination"],
            "departure_date": parsed[0]["departure_at"].date() if parsed[0]["departure_at"] else datetime.date.today(),
            "segments": parsed,
        }
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 1. LOG SEARCH REQUEST
# ═══════════════════════════════════════════════════════════════════════════

def log_search_request(
    request: FlightSearchRequest,
    supplier: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    search_id: Optional[str] = None,
    result_count: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    status: str = "success",
) -> None:
    db = next(get_ota_db_session())
    try:
        trip_type = "ROUND_TRIP" if request.return_date else "ONE_WAY"
        entry = SearchRequest(
            search_id    = search_id or str(uuid.uuid4()),
            user_id      = user_id,
            session_id   = session_id,
            supplier     = supplier,
            trip_type    = trip_type,
            cabin_class  = (request.cabin_class or "Y").upper(),
            adults       = request.adults,
            children     = request.children,
            infants      = request.infants,
            origin       = request.origin.upper(),
            destination  = request.destination.upper(),
            departure_date = datetime.date.fromisoformat(request.departure_date),
            return_date  = (
                datetime.date.fromisoformat(request.return_date)
                if request.return_date else None
            ),
            currency     = request.currency or "BDT",
            result_count = result_count,
            request_metadata = metadata,
            status       = status,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.log_search_request", type="warning")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 2. LOG BOOKING (PNR CREATION)
# ═══════════════════════════════════════════════════════════════════════════

def log_booking(
    request: FlightBookingRequest,
    response: Dict[str, Any],
    supplier_code: str,
    user_id: Optional[str] = None,
) -> None:
    """
    Logs a successful booking (PNR creation) to the database.
    Creates: Booking → Journeys → Segments → Passengers → PricingSnapshot → Components → AuditEvent
    """
    db = next(get_ota_db_session())
    try:
        # ── 1. Resolve Supplier ───────────────────────────────────────────
        supplier = db.query(Supplier).filter(Supplier.code.ilike(f"{supplier_code}%")).first()
        supplier_id = supplier.id if supplier else None

        # ── 2. Find PNR in response ──────────────────────────────────────
        pnr = _find_pnr(response)
        if not pnr:
            write_log(f"Could not find PNR in response: {response}",
                      source="flight.logger.log_booking", type="warning")
            return

        # ── 3. Currency & conversion ─────────────────────────────────────
        pi = request.price_info
        write_log(f"[log_booking] price_info received: {pi}",
                  source="flight.logger.log_booking", type="info")

        search_currency = (pi.get("currency") or "BDT").upper()
        conversion_rate = _get_conversion_rate(db, search_currency)

        prices = _extract_price_info(pi)
        
        # Base and Tax
        base_fare       = convert_to_bdt(prices["base"],        search_currency, conversion_rate)
        tax_amount      = convert_to_bdt(prices["tax"],         search_currency, conversion_rate)
        
        # MOCK overrides for commission, discount, and service fee (per user request)
        from app.helpers.flight.commission import calculate_mock_commission
        mock_comm = calculate_mock_commission(base_fare)
        commission_amt  = mock_comm["total"]
        service_fee     = base_fare * Decimal("0.015")  # 1.5% mock service fee
        discount_amount = base_fare * Decimal("0.02")   # 2% mock discount
        
        # Recalculate total with mocks applied
        total_amount    = base_fare + tax_amount + service_fee - discount_amount

        write_log(
            f"[log_booking] MOCK applied. Amounts → total: {total_amount} BDT, base: {base_fare} BDT "
            f"(from {search_currency} raw: {prices['total']} @ {conversion_rate})",
            source="flight.logger.log_booking", type="info"
        )

        # ── 4. Determine journey type & Extract fields ────────────────────────────────────
        trip_type_raw = pi.get("trip_type") or pi.get("tripType") or None
        if not trip_type_raw:
            # Infer from segments: if first origin == last destination, it's round trip
            segs = request.flight_segments
            if len(segs) >= 2:
                first_orig = _extract_segment_fields(segs[0], 0)["origin"]
                last_dest = _extract_segment_fields(segs[-1], len(segs) - 1)["destination"]
                trip_type_raw = "round_trip" if first_orig == last_dest else "one_way"
            else:
                trip_type_raw = "one_way"

        journey_type = trip_type_raw.upper().replace("-", "_")

        pcc = _find_pcc(response)
        ttl = _find_ttl(response)

        booking = AtBooking(
            booking_reference = f"SN{uuid.uuid4().hex[:8].upper()}",
            user_id           = int(user_id) if user_id and str(user_id).isdigit() else None,
            supplier_id       = supplier_id,
            status            = 'CONFIRMED' if pnr else 'PENDING',
            booking_status    = 'CONFIRMED' if pnr else 'PENDING',
            journey_type      = journey_type,
            primary_pnr       = pnr,
            pnr               = pnr,       # Legacy field for backward compat
            supplier_booking_id = pnr,
            contact_email     = request.passengers[0].email if request.passengers and request.passengers[0].email else "",
            contact_phone     = request.passengers[0].phone if request.passengers and request.passengers[0].phone else "",
            booking_date      = datetime.datetime.utcnow(),
            pcc               = pcc,
            ticketing_time_limit = ttl,
            booking_expiry    = ttl,
            gds_source        = supplier_code,
            
            # Legacy Pricing fields for backward compatibility
            currency          = search_currency,
            search_currency   = search_currency,
            conversion_rate   = conversion_rate,
            base_fare         = base_fare,
            tax_amount        = tax_amount,
            service_fee       = service_fee,
            discount_amount   = discount_amount,
            total_amount      = total_amount,
            commission_amount = commission_amt,
            airline_code      = request.flight_segments[0].get("marketing_carrier", request.flight_segments[0].get("carrier_code")) if request.flight_segments else None,
        )
        db.add(booking)
        db.flush()

        # ── 6. Create Journeys & Segments ────────────────────────────────
        journey_groups = _build_journeys(request.flight_segments, trip_type_raw)
        journey_objects = []
        all_segment_objects = []

        for j_idx, j_data in enumerate(journey_groups):
            journey = AtBookingJourney(
                booking_id       = booking.id,
                journey_sequence = j_idx + 1,
                direction        = j_data["direction"],
                origin           = j_data["origin"],
                destination      = j_data["destination"],
                departure_date   = j_data["departure_date"],
            )
            db.add(journey)
            db.flush()
            journey_objects.append(journey)

            for s_idx, s_data in enumerate(j_data["segments"]):
                
                orig_an, orig_cn = _get_location_names(db, s_data["origin"])
                dest_an, dest_cn = _get_location_names(db, s_data["destination"])
                
                segment = AtBookingSegment(
                    booking_id        = booking.id,
                    journey_id        = journey.id,
                    segment_number    = s_data["segment_number"],
                    segment_sequence  = s_idx + 1,
                    carrier_code      = s_data["carrier_code"],
                    marketing_carrier = s_data["marketing_carrier"],
                    operating_carrier = s_data["operating_carrier"],
                    flight_number     = s_data["flight_number"],
                    origin            = s_data["origin"],
                    destination       = s_data["destination"],
                    departure_at      = s_data["departure_at"],
                    arrival_at        = s_data["arrival_at"],
                    cabin_class       = s_data["cabin_class"],
                    booking_class     = s_data["booking_class"],
                    fare_basis        = s_data["fare_basis"],
                    aircraft_code     = s_data["aircraft_code"],
                    stop_quantity     = s_data["stop_quantity"],
                    duration_minutes  = s_data.get("duration_minutes"),
                    baggage_allowance = s_data.get("baggage_allowance"),
                    baggage_info      = s_data.get("baggage_info"),
                    terminal_departure= s_data.get("terminal_departure"),
                    terminal_arrival  = s_data.get("terminal_arrival"),
                    
                    # Legacy fields
                    departure_airport = s_data["origin"],
                    arrival_airport   = s_data["destination"],
                    departure_time    = s_data["departure_at"],
                    arrival_time      = s_data["arrival_at"],
                    segment_order     = s_idx + 1,
                    status            = 'HK', # Common legacy status for confirmed
                    duration          = str(s_data.get("duration_raw")) if s_data.get("duration_raw") else None,
                    
                    # Detailed Location Info
                    departure_airport_name = orig_an,
                    arrival_airport_name   = dest_an,
                    departure_city_name    = orig_cn,
                    arrival_city_name      = dest_cn,
                )
                db.add(segment)
                all_segment_objects.append(segment)

        db.flush()

        # ── 7. Create Passengers ─────────────────────────────────────────
        passenger_objects = []
        for pax_idx, pax in enumerate(request.passengers):
            ptype = (pax.passenger_type or "ADT").upper().strip()
            # Normalise type codes
            type_map = {"CNN": "CHD", "CHILD": "CHD", "ADULT": "ADT", "INFANT": "INF"}
            ptype = type_map.get(ptype, ptype)
            if ptype not in ("ADT", "CHD", "INF", "INS"):
                ptype = "ADT"

            passenger = AtBookingPassenger(
                booking_id     = booking.id,
                type           = ptype,
                is_lead        = 1 if pax_idx == 0 else 0,
                title          = getattr(pax, "title", None),
                first_name     = pax.first_name,
                last_name      = pax.last_name,
                gender         = pax.gender,
                dob            = _parse_date(pax.date_of_birth),
                passport_no    = pax.document_number,
                passport_expiry= _parse_date(getattr(pax, "document_expiry", None)),
                issuing_country= getattr(pax, "document_issue_country", None),
                nationality    = getattr(pax, "nationality", None),
                email          = pax.email,
                phone          = pax.phone,
                
                # Legacy alias fields
                passenger_type = ptype,
                date_of_birth  = _parse_date(pax.date_of_birth),
                passport_issuing_country = getattr(pax, "document_issue_country", None),
            )
            db.add(passenger)
            passenger_objects.append(passenger)

        db.flush()

        # ── 8. Create Pricing Snapshot & Components ──────────────────────
        customer_total = total_amount  # base + tax + service_fee - discount
        supplier_total = base_fare + tax_amount

        snapshot = AtPricingSnapshot(
            booking_id      = booking.id,
            operation       = 'BOOK',
            source          = 'SABRE',  # or fallback to general 'SYSTEM' if supplier_code not known
            supplier_id     = supplier_id,
            created_by      = str(user_id) if user_id else 'SYSTEM',
            status          = 'ACTIVE',
            version         = 1,
            is_active       = True,
            base_currency   = DEFAULT_CURRENCY,
            search_currency = search_currency,
            conversion_rate = conversion_rate,
            supplier_total  = supplier_total,
            customer_total  = customer_total,
            commission_total = commission_amt,
        )
        db.add(snapshot)
        db.flush()

        # Build pricing components
        components = []
        if base_fare > 0:
            components.append(AtPricingComponent(
                pricing_snapshot_id = snapshot.id,
                component_type      = 'BASE_FARE',
                scope               = 'SUPPLIER',
                direction           = 'DEBIT',
                source              = 'AIRLINE',
                amount              = base_fare,
                original_amount     = base_fare,
                original_currency   = DEFAULT_CURRENCY,
                exchange_rate       = conversion_rate,
                converted_amount    = base_fare,
                converted_currency  = DEFAULT_CURRENCY,
                currency_code       = DEFAULT_CURRENCY,
                is_refundable       = True,
                supplier_id         = supplier_id,
            ))
            
        if prices.get("tax_breakdown"):
            for t_item in prices["tax_breakdown"]:
                t_amt_bdt = convert_to_bdt(t_item["amount"], search_currency, conversion_rate)
                if t_amt_bdt > 0:
                    components.append(AtPricingComponent(
                        pricing_snapshot_id = snapshot.id,
                        component_type      = 'TAX',
                        code                = t_item["code"],
                        scope               = 'SUPPLIER',
                        direction           = 'DEBIT',
                        source              = 'GOVERNMENT' if t_item["code"] not in ['YQ', 'YR'] else 'AIRLINE',
                        amount              = t_amt_bdt,
                        original_amount     = Decimal(str(t_item["amount"])),
                        original_currency   = search_currency,
                        exchange_rate       = conversion_rate,
                        converted_amount    = t_amt_bdt,
                        converted_currency  = DEFAULT_CURRENCY,
                        currency_code       = DEFAULT_CURRENCY,
                        is_refundable       = True,
                        supplier_id         = supplier_id,
                    ))
        elif tax_amount > 0:
            components.append(AtPricingComponent(
                pricing_snapshot_id = snapshot.id,
                component_type      = 'TAX',
                scope               = 'SUPPLIER',
                direction           = 'DEBIT',
                source              = 'AIRLINE',
                amount              = tax_amount,
                original_amount     = Decimal(str(prices["tax"])) if prices["tax"] else None,
                original_currency   = search_currency,
                exchange_rate       = conversion_rate,
                converted_amount    = tax_amount,
                converted_currency  = DEFAULT_CURRENCY,
                currency_code       = DEFAULT_CURRENCY,
                is_refundable       = True,
                supplier_id         = supplier_id,
            ))
            
        if service_fee > 0:
            components.append(AtPricingComponent(
                pricing_snapshot_id = snapshot.id,
                component_type      = 'FEE',
                component_subtype   = 'SERVICE',
                scope               = 'CUSTOMER',
                direction           = 'DEBIT',
                source              = 'OTA',
                amount              = service_fee,
                original_amount     = service_fee,
                original_currency   = DEFAULT_CURRENCY,
                exchange_rate       = Decimal("1.000000"),
                converted_amount    = service_fee,
                converted_currency  = DEFAULT_CURRENCY,
                currency_code       = DEFAULT_CURRENCY,
                description         = 'Service fee',
                is_refundable       = False,
            ))
        if discount_amount > 0:
            components.append(AtPricingComponent(
                pricing_snapshot_id = snapshot.id,
                component_type      = 'DISCOUNT',
                code                = 'PROMO',
                scope               = 'CUSTOMER',
                direction           = 'CREDIT',
                source              = 'OTA',
                amount              = discount_amount,
                original_amount     = discount_amount,
                original_currency   = DEFAULT_CURRENCY,
                exchange_rate       = Decimal("1.000000"),
                converted_amount    = discount_amount,
                converted_currency  = DEFAULT_CURRENCY,
                currency_code       = DEFAULT_CURRENCY,
                is_refundable       = False,
            ))
        if mock_comm["total"] > 0:
            for comm_item in mock_comm["breakdown"]:
                if comm_item["amount"] > 0:
                    components.append(AtPricingComponent(
                        pricing_snapshot_id = snapshot.id,
                        component_type      = 'COMMISSION',
                        code                = comm_item["code"],
                        scope               = 'INTERNAL',
                        direction           = 'CREDIT',
                        source              = 'AIRLINE',
                        amount              = comm_item["amount"],
                        original_amount     = comm_item["amount"],
                        original_currency   = DEFAULT_CURRENCY,
                        exchange_rate       = Decimal("1.000000"),
                        converted_amount    = comm_item["amount"],
                        converted_currency  = DEFAULT_CURRENCY,
                        currency_code       = DEFAULT_CURRENCY,
                        percentage          = comm_item.get("percentage"),
                        calculation_basis   = base_fare,
                        description         = comm_item.get("description"),
                        is_refundable       = False,
                        supplier_id         = supplier_id,
                    ))

        for comp in components:
            db.add(comp)

        # ── 9. Record Audit Event ────────────────────────────────────────
        audit = AtAuditEvent(
            booking_id = booking.id,
            event_type = 'STATUS_CHANGE',
            old_value  = None,
            new_value  = 'CONFIRMED' if pnr else 'PENDING',
            details    = {"pnr": pnr, "supplier": supplier_code},
            actor_type = 'SYSTEM',
        )
        db.add(audit)

        # ── 10. Legacy: Record Status History (kept for backward compat) ─
        history = AtBookingStatusHistory(
            booking_id = booking.id,
            old_status = None,
            new_status = 'CONFIRMED' if pnr else 'PENDING',
            remarks    = "Booking created and confirmed by supplier"
        )
        db.add(history)

        db.commit()
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.log_booking", type="error")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 3. LOG TICKET ISSUANCE
# ═══════════════════════════════════════════════════════════════════════════
def log_ticket(
    request: TicketingRequest,
    response: Dict[str, Any],
    supplier_code: str,
    user_id: Optional[int] = None
) -> None:
    """
    Logs ticket issuance to the database.
    Creates: Tickets → TicketCoupons → new PricingSnapshot → AuditEvent
    """
    db = next(get_ota_db_session())
    try:
        # ── 1. Find booking ──────────────────────────────────────────────
        booking = db.query(AtBooking).filter(
            (AtBooking.pnr == request.pnr) | (AtBooking.primary_pnr == request.pnr)
        ).first()
        if not booking:
            write_log(f"Booking not found for PNR {request.pnr}",
                      source="flight.logger.log_ticket", type="warning")
            return

        # ── 2. Check ticketing success ───────────────────────────────────
        air_ticket_rs = response.get("AirTicketRS", {})
        app_results = air_ticket_rs.get("ApplicationResults", {})
        rs_status = app_results.get("status")
        is_success = rs_status == "Complete" or response.get("status") == "Success"

        if not is_success:
            error_details = _extract_ticketing_errors(app_results)
            err_msg = "; ".join(error_details) if error_details else "Unknown error during ticketing"

            # Record failure as audit event
            db.add(AtAuditEvent(
                booking_id = booking.id,
                event_type = 'SYSTEM',
                details    = {"action": "TICKET_FAILED", "error": err_msg},
                actor_type = 'SYSTEM',
            ))
            db.add(AtBookingStatusHistory(
                booking_id = booking.id,
                old_status = booking.status,
                new_status = booking.status,
                remarks    = f"Ticketing failed: {err_msg}"
            ))
            db.commit()
            write_log(f"Ticketing failed for PNR {request.pnr}: {err_msg}",
                      source="flight.logger.log_ticket", type="warning")
            return

        # ── 3. Parse ticket numbers from response ────────────────────────
        parsed_tickets = _parse_ticket_numbers(response)

        # ── 4. Fetch passengers & segments ───────────────────────────────
        passengers = db.query(AtBookingPassenger).filter(
            AtBookingPassenger.booking_id == booking.id
        ).order_by(AtBookingPassenger.id).all()

        segments = db.query(AtBookingSegment).filter(
            AtBookingSegment.booking_id == booking.id
        ).order_by(AtBookingSegment.segment_number).all()

        # ── 5. Match tickets to passengers ───────────────────────────────
        ticket_pax_mapping = _match_tickets_to_passengers(parsed_tickets, passengers)

        # ── 6. Upsert tickets & create coupons ───────────────────────────
        for index, passenger in enumerate(passengers):
            ticket_number = None
            for t_num, pax in ticket_pax_mapping.items():
                if pax.id == passenger.id:
                    ticket_number = t_num
                    break

            if not ticket_number and index < len(parsed_tickets):
                ticket_number = parsed_tickets[index]["ticket_number"]

            existing_ticket = db.query(AtFlightTicket).filter(
                AtFlightTicket.booking_id == booking.id,
                AtFlightTicket.passenger_id == passenger.id
            ).first()

            if existing_ticket:
                existing_ticket.ticket_number = ticket_number
                existing_ticket.status = 'ISSUED'
                existing_ticket.pnr = request.pnr
                existing_ticket.issued_at = datetime.datetime.utcnow()
                existing_ticket.validating_carrier = request.validating_carrier
                ticket_obj = existing_ticket
            else:
                ticket_obj = AtFlightTicket(
                    booking_id         = booking.id,
                    passenger_id       = passenger.id,
                    ticket_number      = ticket_number,
                    status             = 'ISSUED',
                    pnr                = request.pnr,
                    validating_carrier = request.validating_carrier,
                    issued_at          = datetime.datetime.utcnow(),
                )
                db.add(ticket_obj)
                db.flush()

            # Create ticket coupons (one per segment)
            for coupon_num, seg in enumerate(segments, start=1):
                existing_coupon = db.query(AtTicketCoupon).filter(
                    AtTicketCoupon.ticket_id == ticket_obj.id,
                    AtTicketCoupon.coupon_number == coupon_num,
                ).first()

                if not existing_coupon:
                    coupon = AtTicketCoupon(
                        ticket_id         = ticket_obj.id,
                        segment_id        = seg.id,
                        coupon_number     = coupon_num,
                        coupon_status     = 'OPEN',
                        
                        # Legacy fields
                        departure_airport = seg.origin,
                        arrival_airport   = seg.destination,
                        departure_time    = seg.departure_at,
                        carrier           = seg.marketing_carrier or seg.carrier_code,
                        flight_number     = seg.flight_number,
                        fare_basis        = seg.fare_basis,
                        booking_class     = seg.booking_class,
                    )
                    db.add(coupon)

        # ── 7. Update booking status ─────────────────────────────────────
        old_status = booking.status
        booking.status = 'TICKETED'
        booking.issued_at = datetime.datetime.utcnow()

        # ── 8. Create new TICKETING pricing snapshot ─────────────────────
        old_snapshot = db.query(AtPricingSnapshot).filter(
            AtPricingSnapshot.booking_id == booking.id,
            AtPricingSnapshot.is_active == True
        ).first()

        if old_snapshot:
            old_snapshot.is_active = False
            old_snapshot.status = 'SUPERSEDED'

            supplier = resolve_supplier(supplier_code)
            supplier_id = supplier.provider_id if hasattr(supplier, 'provider_id') else None

            new_snapshot = AtPricingSnapshot(
                booking_id       = booking.id,
                operation        = 'TICKET',
                source           = 'SABRE',
                supplier_id      = supplier_id,
                created_by       = str(user_id) if user_id else 'SYSTEM',
                status           = 'ACTIVE',
                version          = old_snapshot.version + 1,
                is_active        = True,
                base_currency    = old_snapshot.base_currency,
                search_currency  = old_snapshot.search_currency,
                conversion_rate  = old_snapshot.conversion_rate,
                supplier_total   = old_snapshot.supplier_total,
                customer_total   = old_snapshot.customer_total,
                commission_total = old_snapshot.commission_total,
            )
            db.add(new_snapshot)
            db.flush()

            # Copy components to new snapshot
            for comp in old_snapshot.components:
                db.add(AtPricingComponent(
                    pricing_snapshot_id = new_snapshot.id,
                    component_type      = comp.component_type,
                    component_subtype   = comp.component_subtype,
                    scope               = comp.scope,
                    direction           = comp.direction,
                    amount              = comp.amount,
                    original_amount     = comp.original_amount,
                    currency_code       = comp.currency_code,
                    description         = comp.description,
                    is_refundable       = comp.is_refundable,
                    passenger_id        = comp.passenger_id,
                    segment_id          = comp.segment_id,
                    journey_id          = comp.journey_id,
                ))

        # ── 9. Record audit event ────────────────────────────────────────
        db.add(AtAuditEvent(
            booking_id = booking.id,
            event_type = 'TICKET_ISSUED',
            old_value  = old_status,
            new_value  = 'TICKETED',
            details    = {
                "tickets": [t["ticket_number"] for t in parsed_tickets],
                "pnr": request.pnr,
                "validating_carrier": request.validating_carrier,
            },
            actor_type = 'SYSTEM',
        ))

        # Legacy: Status History
        db.add(AtBookingStatusHistory(
            booking_id = booking.id,
            old_status = old_status,
            new_status = 'TICKETED',
            remarks    = "Ticket(s) issued successfully"
        ))

        db.commit()
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.log_ticket", type="error")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 4. LOG SUPPLIER CALL
# ═══════════════════════════════════════════════════════════════════════════

def log_supplier_call(
    supplier_code: str,
    endpoint: str,
    request_payload: Any,
    response_payload: Any,
    response_time_ms: int,
    status_code: int,
    booking_id: Optional[int] = None,
    supplier_booking_ref: Optional[str] = None,
    pcc: Optional[str] = None,
    gds_source: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """
    Logs raw supplier API calls for debugging and auditing.
    All supplier-specific data is isolated here.
    """
    db = next(get_ota_db_session())
    try:
        supplier = db.query(Supplier).filter(Supplier.code == supplier_code).first()
        entry = SupplierTransaction(
            supplier_id          = supplier.id if supplier else None,
            booking_id           = booking_id,
            operation            = endpoint[:50],
            supplier_booking_ref = supplier_booking_ref,
            pcc                  = pcc,
            gds_source           = gds_source,
            http_status_code     = status_code,
            response_time_ms     = response_time_ms,
            error_message        = error_message,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.log_supplier_call", type="warning")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# 5. UPDATE BOOKING STATUS
# ═══════════════════════════════════════════════════════════════════════════

def update_booking_status(
    booking_id: str,
    new_status: str,
    remarks: Optional[str] = None,
    changed_by: Optional[str] = None
) -> bool:
    """
    Updates booking status and records the change in both
    audit events and legacy status history.
    """
    db = next(get_ota_db_session())
    try:
        booking = db.query(AtBooking).filter(AtBooking.id == booking_id).first()
        if not booking:
            return False

        old_status = booking.status
        booking.status = new_status

        # Audit event
        db.add(AtAuditEvent(
            booking_id = booking.id,
            event_type = 'STATUS_CHANGE',
            old_value  = old_status,
            new_value  = new_status,
            details    = {"remarks": remarks} if remarks else None,
            actor_type = 'USER' if changed_by else 'SYSTEM',
            actor_id   = changed_by,
        ))

        # Legacy status history
        db.add(AtBookingStatusHistory(
            booking_id = booking.id,
            old_status = old_status,
            new_status = new_status,
            remarks    = remarks,
            changed_by = changed_by
        ))

        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.update_booking_status", type="error")
        return False
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# Private helpers
# ═══════════════════════════════════════════════════════════════════════════

def _find_pnr(res: Any) -> Optional[str]:
    """Recursively search a response dict for a PNR (6-char alnum uppercase)."""
    if not res:
        return None
    if isinstance(res, str):
        if len(res) == 6 and res.isalnum() and res.isupper():
            return res
        return None
    if isinstance(res, dict):
        for key in ["ID", "pnr", "id", "bookingId", "confirmationId", "RecordLocator"]:
            val = res.get(key)
            if val and isinstance(val, str) and len(val) == 6 and val.isalnum() and val.isupper():
                return val
        for v in res.values():
            found = _find_pnr(v)
            if found:
                return found
    elif isinstance(res, list):
        for item in res:
            found = _find_pnr(item)
            if found:
                return found
    return None

def _find_pcc(res: Any) -> Optional[str]:
    """Recursively search for a PCC (Pseudo City Code)."""
    if not res:
        return None
    if isinstance(res, dict):
        for key in ["pcc", "PCC", "PseudoCityCode", "pseudoCityCode"]:
            val = res.get(key)
            if val and isinstance(val, str) and len(val) >= 3:
                return val
        for v in res.values():
            found = _find_pcc(v)
            if found:
                return found
    elif isinstance(res, list):
        for item in res:
            found = _find_pcc(item)
            if found:
                return found
    return None

def _find_ttl(res: Any) -> Optional[datetime.datetime]:
    """Recursively search for ticketing time limit."""
    if not res:
        return None
    if isinstance(res, dict):
        for key in ["ticketingTimeLimit", "TicketingTimeLimit", "timeLimit", "TimeLimit", "TKT_TimeLimit"]:
            val = res.get(key)
            if val and isinstance(val, str):
                return _parse_dt(val)
        for v in res.values():
            found = _find_ttl(v)
            if found:
                return found
    elif isinstance(res, list):
        for item in res:
            found = _find_ttl(item)
            if found:
                return found
    return None


def _extract_ticketing_errors(app_results: Dict) -> List[str]:
    """Extract error messages from Sabre AirTicketRS ApplicationResults."""
    error_details = []
    for section in ["Warning", "Error"]:
        for item in app_results.get(section, []):
            for sys_res in item.get("SystemSpecificResults", []):
                for msg in sys_res.get("Message", []):
                    content = msg.get("content") or msg.get("value")
                    if content and content not in error_details:
                        error_details.append(content)
    return error_details


def _parse_ticket_numbers(response: Dict) -> List[Dict[str, str]]:
    """Extract ticket numbers from a Sabre AirTicketRS response."""
    tickets_data = response.get("AirTicketRS", {}).get("Summary", [])
    if not tickets_data:
        tickets_data = response.get("AirTicketRS", {}).get("TicketDetails", [])

    parsed = []
    if tickets_data:
        for t_data in tickets_data:
            if isinstance(t_data, dict):
                num = t_data.get("TicketNumber") or t_data.get("DocumentNumber") or t_data.get("number")
                pax_name = t_data.get("PassengerName") or ""
                if num:
                    parsed.append({"ticket_number": str(num), "passenger_name": str(pax_name)})
            elif isinstance(t_data, str):
                parsed.append({"ticket_number": t_data, "passenger_name": ""})

    # Fallback: recursive search for ticket numbers
    if not parsed:
        ticket_numbers = []
        def find_tickets(obj):
            if isinstance(obj, dict):
                if "TicketNumber" in obj:
                    ticket_numbers.append(obj["TicketNumber"])
                elif "DocumentNumber" in obj:
                    ticket_numbers.append(obj["DocumentNumber"])
                for v in obj.values():
                    find_tickets(v)
            elif isinstance(obj, list):
                for item in obj:
                    find_tickets(item)
        find_tickets(response)
        for tn in ticket_numbers:
            if tn:
                parsed.append({"ticket_number": str(tn), "passenger_name": ""})

    return parsed


def _match_tickets_to_passengers(
    parsed_tickets: List[Dict[str, str]],
    passengers: List[AtBookingPassenger],
) -> Dict[str, AtBookingPassenger]:
    """Match ticket numbers to passengers by name, falling back to order."""
    def normalize_name(name_str):
        if not name_str:
            return ""
        clean = "".join(c for c in name_str.upper() if c.isalnum())
        for title in ["MR", "MRS", "MS", "MSTR", "MISS", "DR"]:
            if clean.endswith(title):
                clean = clean[:-len(title)]
        return clean

    used_pax_ids = set()
    mapping = {}

    for t in parsed_tickets:
        t_num = t["ticket_number"]
        pax_name_str = t["passenger_name"]
        matched_pax = None

        if pax_name_str:
            pax_name_norm = normalize_name(pax_name_str)
            for p in passengers:
                if p.id in used_pax_ids:
                    continue
                p_first_norm = normalize_name(p.first_name)
                p_last_norm = normalize_name(p.last_name)
                if p_last_norm in pax_name_norm and p_first_norm in pax_name_norm:
                    matched_pax = p
                    break

        if not matched_pax:
            for p in passengers:
                if p.id not in used_pax_ids:
                    matched_pax = p
                    break

        if matched_pax:
            used_pax_ids.add(matched_pax.id)
            mapping[t_num] = matched_pax

    return mapping
