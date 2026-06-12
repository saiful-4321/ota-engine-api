import uuid
import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from sqlalchemy import text

from app.models.sabre_schemas import FlightSearchRequest, FlightBookingRequest, TicketingRequest
from app.models.otadb.SearchRequest import SearchRequest
from app.models.otadb.Booking import Booking
from app.models.otadb.BookingSegment import BookingSegment
from app.models.otadb.BookingPassenger import BookingPassenger
from app.models.otadb.Ticket import Ticket
from app.models.otadb.Supplier import Supplier
from app.models.otadb.SupplierLog import SupplierLog
from app.models.otadb.Payment import Payment
from app.models.otadb.Refund import Refund
from app.models.otadb.BookingStatusHistory import BookingStatusHistory
from app.helpers.common import get_ota_db_session, write_log
from app.utils.currency import convert_to_bdt, normalize_rate, DEFAULT_CURRENCY


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

def _parse_dt(dt_str: Any) -> datetime.datetime:
    """Helper to parse datetime strings safely."""
    if not dt_str or not isinstance(dt_str, str):
        return datetime.datetime.utcnow()
    try:
        # Remove 'Z' if present and replace 'T' with space
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
def log_booking(
    request: FlightBookingRequest,
    response: Dict[str, Any],
    supplier_code: str,
    user_id: Optional[str] = None,
) -> None:
    """
    Logs a successful booking (PNR creation) to the database.
    """
    db = next(get_ota_db_session())
    try:
        # 1. Resolve Supplier ID
        supplier = db.query(Supplier).filter(Supplier.code == supplier_code).first()
        supplier_id = supplier.id if supplier else None

        # 2. Extract PNR from Sabre Response
        # Note: Response structure varies by supplier. This assumes Sabre format.
        def _find_pnr(res: Any) -> Optional[str]:
            if not res:
                return None
            if isinstance(res, str):
                if len(res) == 6 and res.isalnum() and res.isupper():
                    return res
                return None
            if isinstance(res, dict):
                # Priority keys
                for key in ["ID", "pnr", "id", "bookingId", "confirmationId", "RecordLocator"]:
                    val = res.get(key)
                    if val and isinstance(val, str) and len(val) == 6 and val.isalnum() and val.isupper():
                        return val
                # Recurse
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

        pnr = _find_pnr(response)

        if not pnr:
            write_log(f"Could not find PNR in response: {response}", source="flight.logger.log_booking", type="warning")
            return

        # 3. Extract Price Info & Currency Context
        pi = request.price_info

        # Log the raw price_info for debugging (helps trace key mismatches)
        write_log(
            f"[log_booking] price_info received: {pi}",
            source="flight.logger.log_booking", type="info"
        )

        # The currency the client searched / priced in (e.g. 'USD', 'SGD', 'BDT')
        search_currency = (pi.get("currency") or "BDT").upper()

        # Fetch conversion rate directly from the 'currencies' table in the DB
        # The frontend no longer needs to pass conversion_rate_to_bdt
        conversion_rate_value = 1.0
        if search_currency != "BDT":
            try:
                result = db.execute(
                    text("SELECT exchange_rate FROM currencies WHERE code = :code AND status = 'Active'"),
                    {"code": search_currency}
                ).fetchone()
                if result and result[0]:
                    conversion_rate_value = float(result[0])
            except Exception as e:
                write_log(f"Failed to fetch exchange rate for {search_currency}: {e}", source="flight.logger.log_booking", type="warning")
        
        conversion_rate = normalize_rate(conversion_rate_value, search_currency)

        # ── Amount extraction ───────────────────────────────────────────────
        # Handles all key variants from:
        #   • Search response  (format_bfm_response)  → baseFare, taxes, numericPrice
        #   • Pricing response (format_pricing_response) → base, taxes, total
        #   • Direct client    (manually built)        → base_fare, tax_amount, total_fare
        # ────────────────────────────────────────────────────────────────────

        # total
        raw_total = (
            pi.get("total_fare")
            or pi.get("totalFare")
            or pi.get("total_amount")
            or pi.get("total_price") # <--- Ah! The frontend is sending this!
            or pi.get("total")
            or pi.get("numericPrice")
            or 0
        )
        # base fare
        raw_base = (
            pi.get("base_fare")
            or pi.get("baseFare")
            or pi.get("base")
            or pi.get("base_price")
            or 0
        )
        # tax
        raw_tax = (
            pi.get("tax_amount")     # manual / legacy
            or pi.get("taxAmount")
            or pi.get("taxes")       # BFM search response & pricing response key
            or 0
        )
        # service fee
        raw_service = (
            pi.get("service_fee")
            or pi.get("serviceFee")
            or 0
        )
        # discount
        raw_discount = (
            pi.get("discount_amount")
            or pi.get("discountAmount")
            or 0
        )

        # If we still have no total but have base+tax, derive it
        if not raw_total and (raw_base or raw_tax):
            raw_total = (float(raw_base or 0) + float(raw_tax or 0) + float(raw_service or 0))

        # If the frontend only sent the total but no breakdown, attribute it to base fare
        if raw_total and not raw_base and not raw_tax:
            raw_base = raw_total

        # Convert to BDT using the fetched conversion rate
        total_amount    = convert_to_bdt(raw_total,    search_currency, conversion_rate)
        base_fare       = convert_to_bdt(raw_base,     search_currency, conversion_rate)
        tax_amount      = convert_to_bdt(raw_tax,      search_currency, conversion_rate)
        service_fee     = convert_to_bdt(raw_service,  search_currency, conversion_rate)
        discount_amount = convert_to_bdt(raw_discount, search_currency, conversion_rate)

        # Log exactly what amounts are going into the DB for verification
        write_log(
            f"[log_booking] Amounts to DB -> total: {total_amount} BDT, base: {base_fare} BDT (from {search_currency} raw: {raw_total} @ {conversion_rate})",
            source="flight.logger.log_booking", type="info"
        )
        
        # 4. Create Booking Header
        booking = Booking(
            booking_reference = f"SN{uuid.uuid4().hex[:8].upper()}",
            user_id           = user_id or "0",
            supplier_id       = supplier_id,
            booking_status    = 'CONFIRMED',
            payment_status    = 'PENDING',
            pnr               = pnr,
            supplier_booking_id = pnr,
            # Stored currency is always BDT
            currency          = DEFAULT_CURRENCY,
            search_currency   = search_currency,
            conversion_rate   = conversion_rate,
            # All amounts in BDT
            base_fare         = base_fare,
            tax_amount        = tax_amount,
            service_fee       = service_fee,
            discount_amount   = discount_amount,
            total_amount      = total_amount,
        )
        db.add(booking)
        db.flush() # Get booking.id

        # 4. Create Segments
        for i, seg in enumerate(request.flight_segments):
            # Try to get dates from various possible keys
            dep_str = seg.get("departure") or seg.get("DepartureDateTime") or ""
            arr_str = seg.get("arrival") or seg.get("ArrivalDateTime") or ""
            
            segment = BookingSegment(
                booking_id     = booking.id,
                segment_number = i + 1,
                airline_code   = seg.get("airline") or seg.get("MarketingAirline", {}).get("Code", "XX"),
                flight_number  = str(seg.get("flight_number") or seg.get("FlightNumber", "")),
                origin         = (seg.get("origin") or seg.get("OriginLocation", {}).get("LocationCode", "")).upper(),
                destination    = (seg.get("destination") or seg.get("DestinationLocation", {}).get("LocationCode", "")).upper(),
                departure_datetime = _parse_dt(dep_str),
                arrival_datetime   = _parse_dt(arr_str),
                cabin_class    = seg.get("cabin_class") or seg.get("ResBookDesigCode", "Y"),
            )
            db.add(segment)

        # 5. Create Passengers
        for pax in request.passengers:
            ptype = (pax.passenger_type or "ADT").upper().strip()
            if ptype in ["CNN", "CHILD"]:
                ptype = "CHD"
            elif ptype in ["ADULT"]:
                ptype = "ADT"
            elif ptype in ["INFANT"]:
                ptype = "INF"
            
            # Keep only ADT, CHD, INF to match passenger_type_enum values
            if ptype not in ["ADT", "CHD", "INF"]:
                ptype = "ADT"

            passenger = BookingPassenger(
                booking_id     = booking.id,
                passenger_type = ptype,
                title          = None,
                first_name     = pax.first_name,
                last_name      = pax.last_name,
                gender         = pax.gender,
                date_of_birth  = _parse_date(pax.date_of_birth),
                passport_number = pax.document_number,
                email          = pax.email,
                phone          = pax.phone,
            )
            db.add(passenger)

        # 6. Record Status History
        history = BookingStatusHistory(
            booking_id = booking.id,
            old_status = None,
            new_status = 'CONFIRMED',
            remarks    = "Booking created and confirmed by supplier"
        )
        db.add(history)

        db.commit()
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.log_booking", type="error")
    finally:
        db.close()

def log_ticket(
    request: TicketingRequest,
    response: Dict[str, Any],
    supplier_code: str,
) -> None:
    """
    Logs ticket issuance to the database.
    """
    db = next(get_ota_db_session())
    try:
        # Find the booking by PNR
        booking = db.query(Booking).filter(Booking.pnr == request.pnr).first()
        if not booking:
            write_log(f"Booking not found for PNR {request.pnr}", source="flight.logger.log_ticket", type="warning")
            return

        # Extract ticket numbers from response
        # Sabre REST 1.3.0 usually returns tickets in AirTicketRS -> Summary
        tickets_data = response.get("AirTicketRS", {}).get("Summary", [])
        if not tickets_data:
            # Fallback for other versions or structures
            tickets_data = response.get("AirTicketRS", {}).get("TicketDetails", [])
        
        # If still empty, try to find any "TicketNumber" in the response (recursive search)
        if not tickets_data:
            ticket_numbers = []
            def find_tickets(obj):
                if isinstance(obj, dict):
                    if "TicketNumber" in obj:
                        ticket_numbers.append(obj["TicketNumber"])
                    for v in obj.values():
                        find_tickets(v)
                elif isinstance(obj, list):
                    for item in obj:
                        find_tickets(item)
            find_tickets(response)
            
            for tn in ticket_numbers:
                tickets_data.append({"TicketNumber": tn})
        
        for t_data in tickets_data:
            ticket_number = t_data.get("TicketNumber")
            pax_name = t_data.get("PassengerName", "") # To link to passenger

            # Simple heuristic to link to passenger by name if possible
            # In a real system, we should have more robust linking
            passenger = db.query(BookingPassenger).filter(
                BookingPassenger.booking_id == booking.id
            ).first() # Just take first for now if we can't link

            # Inherit currency context from parent booking record
            ticket = Ticket(
                booking_id      = booking.id,
                passenger_id    = passenger.id if passenger else None,
                ticket_number   = ticket_number,
                ticket_status   = 'ISSUED',
                validating_carrier = request.validating_carrier,
                issue_date      = datetime.datetime.utcnow(),
                # All amounts in BDT — inherit rate context from booking
                search_currency = booking.search_currency or DEFAULT_CURRENCY,
                conversion_rate = booking.conversion_rate or Decimal("1.000000"),
                total_amount    = booking.total_amount,
                base_fare       = booking.base_fare,
                tax_amount      = booking.tax_amount,
            )
            db.add(ticket)
        
        old_status = booking.booking_status
        booking.booking_status = 'TICKETED'
        booking.issued_at = datetime.datetime.utcnow()
        
        # Record Status History
        history = BookingStatusHistory(
            booking_id = booking.id,
            old_status = old_status,
            new_status = 'TICKETED',
            remarks    = "Ticket(s) issued successfully"
        )
        db.add(history)
        
        db.commit()
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.log_ticket", type="error")
    finally:
        db.close()

def log_supplier_call(
    supplier_code: str,
    endpoint: str,
    request_payload: Any,
    response_payload: Any,
    response_time_ms: int,
    status_code: int
) -> None:
    """
    Logs raw supplier API calls for debugging and auditing.
    """
    db = next(get_ota_db_session())
    try:
        supplier = db.query(Supplier).filter(Supplier.code == supplier_code).first()
        entry = SupplierLog(
            supplier_id      = supplier.id if supplier else None,
            endpoint         = endpoint,
            request_payload  = request_payload,
            response_payload = response_payload,
            response_time_ms = response_time_ms,
            status_code      = status_code
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.log_supplier_call", type="warning")
    finally:
        db.close()

def update_booking_status(
    booking_id: str,
    new_status: str,
    remarks: Optional[str] = None,
    changed_by: Optional[str] = None
) -> bool:
    """
    Updates booking status and records the change in history.
    """
    db = next(get_ota_db_session())
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return False

        old_status = booking.booking_status
        booking.booking_status = new_status
        
        history = BookingStatusHistory(
            booking_id = booking.id,
            old_status = old_status,
            new_status = new_status,
            remarks    = remarks,
            changed_by = changed_by
        )
        db.add(history)
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.update_booking_status", type="error")
        return False
    finally:
        db.close()
