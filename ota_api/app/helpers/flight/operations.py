"""
app/helpers/flight/operations.py

Pricing, booking, post-booking and ancillary workflows behind the flight endpoints. Every money-moving action
(issue, exchange/reissue, refund) re-checks the price with the supplier through the price guard
before anything is submitted.

Each function takes the validated request, the optional `?supplier=` value and (where the action
is recorded) the acting user id, and returns the response body. Errors are raised and mapped to
HTTP statuses by responses.handle_errors.
"""

from typing import Any, Dict, Optional

from app.helpers.common import write_log
from app.helpers.flight.logger import (
    get_booking_snapshot, log_booking, log_refund, log_ticket, log_ticket_status_change, to_bdt,
)
from app.helpers.flight.price_guard import (
    assert_charge_confirmed, assert_refund_confirmed, consume_quote, load_quote, save_quote,
    supplier_tolerance, update_quote,
)
from app.helpers.flight.registry import resolve_request_service, resolve_supplier
from app.utils.flight.errors import PartialExchangeError, PriceChangedError
from app.models.flight_schemas import (
    BaggageAllowanceRequest, CancelItineraryRequest, ExchangeQuoteRequest, ExchangeTicketRequest,
    FareRulesRequest, FlightBookingRequest, FlightPricingRequest, PNRDetailsRequest, QueueRequest,
    RefundQuoteRequest, RefundTicketRequest, RepricePNRRequest, SeatMapRequest, TicketingRequest,
    VoidTicketRequest,
)
from app.utils.flight import (
    format_cancel_response, format_exchange_response, format_fare_rules_response, format_pnr_details_response,
    format_pnr_response, format_pricing_response, format_refund_response, format_ticketing_response,
)


def _public_quote(quote: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in quote.items() if k not in ("context", "raw_response")}


def _client_total(price_info: Dict[str, Any]) -> Optional[float]:
    for key in ("total_fare", "totalFare", "total_amount", "total_price", "total", "numericPrice"):
        if price_info.get(key) not in (None, ""):
            try:
                return float(price_info[key])
            except (TypeError, ValueError):
                return None
    return None


# ── Pricing ──────────────────────────────────────────────────────────────────

def price_flight(request: FlightPricingRequest, query_supplier: Optional[str]) -> Dict[str, Any]:
    svc = resolve_request_service(request, query_supplier)
    formatted = format_pricing_response(svc.integration_provider, svc.price_flight(request))
    if isinstance(formatted, dict):
        formatted["supplier_code"] = svc.supplier_code
    return formatted


# ── Booking ──────────────────────────────────────────────────────────────────

def _verified_booking_price(svc: Any, request: FlightBookingRequest, response: Dict[str, Any]):
    """
    Compares the supplier's stored PNR fare with the client's price.
    Returns (price_check, request_to_log) — the logged request carries the supplier fare, never the client's.
    """
    booked = svc.extract_booked_price(response)
    client_total = _client_total(request.price_info)
    price_check = {
        "verified": bool(booked.get("total_fare")),
        "supplier_total": booked.get("total_fare"),
        "supplier_currency": booked.get("currency"),
        "client_total": client_total,
        "changed": False,
    }
    if not booked.get("total_fare"):
        write_log(f"[Book] Supplier price not found in {svc.supplier_code} response; recording client price",
                  source="flight.operations.book", type="warning")
        return price_check, request

    currency = booked.get("currency") or request.price_info.get("currency") or "BDT"
    price_check["changed"] = (
        client_total is not None
        and str(request.price_info.get("currency") or currency).upper() == str(currency).upper()
        and abs(client_total - booked["total_fare"]) > float(supplier_tolerance(svc))
    )
    log_request = request.copy(update={"price_info": {
        "total_fare": booked["total_fare"],
        "base_fare":  booked.get("base_fare") or 0,
        "tax_amount": booked.get("tax_amount") or 0,
        "currency":   currency,
        "trip_type":  request.price_info.get("trip_type") or request.price_info.get("tripType"),
    }})
    return price_check, log_request


def book(request: FlightBookingRequest, query_supplier: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
    svc = resolve_request_service(request, query_supplier)
    response = svc.create_pnr(request)
    formatted = format_pnr_response(svc.integration_provider, response)

    price_check, log_request = _verified_booking_price(svc, request, response)
    record_saved = log_booking(request=log_request, response=response,
                               supplier_code=svc.supplier_code, user_id=user_id)
    if not record_saved:
        write_log(f"[Book] BOOKING NOT RECORDED in DB for supplier {svc.supplier_code}: {formatted}",
                  source="flight.operations.book", type="error")

    if isinstance(formatted, dict):
        formatted["supplier_code"] = svc.supplier_code
        formatted["price_check"] = price_check
        formatted["record_saved"] = record_saved
        formatted["ticketable"] = price_check["verified"]
        if not price_check["verified"]:
            formatted["warning"] = (
                "The supplier did not store a price for this booking, so it cannot be ticketed. "
                "Reprice the PNR (/pnr/reprice) once all segments are confirmed, or cancel and rebook."
            )
    return formatted


def pnr_details(request: PNRDetailsRequest, query_supplier: Optional[str]) -> Dict[str, Any]:
    svc = resolve_request_service(request, query_supplier, get_booking_snapshot(request.pnr))
    return format_pnr_details_response(svc.integration_provider, svc.get_pnr_details(request))


def cancel_pnr(request: CancelItineraryRequest, query_supplier: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
    snapshot = get_booking_snapshot(request.pnr)
    if snapshot and snapshot["issued_tickets"]:
        raise ValueError(
            f"PNR {request.pnr} has issued tickets {snapshot['issued_tickets']}. "
            f"Void (/ticket/void) or refund (/ticket/refund) them before cancelling."
        )
    svc = resolve_request_service(request, query_supplier, snapshot)
    formatted = format_cancel_response(svc.integration_provider, svc.cancel_itinerary(request))
    if isinstance(formatted, dict) and formatted.get("status") == "success":
        log_ticket_status_change(request.pnr, [], "CANCELLED", "CANCEL",
                                 user_id=user_id, booking_status="CANCELLED")
    return formatted


def reprice_pnr(request: RepricePNRRequest, query_supplier: Optional[str]) -> Dict[str, Any]:
    snapshot = get_booking_snapshot(request.pnr)
    svc = resolve_request_service(request, query_supplier, snapshot)
    result = svc.reprice_pnr(
        pnr=request.pnr,
        passenger_types=request.passenger_types or (snapshot or {}).get("passenger_types"),
        validating_carrier=request.validating_carrier,
    )
    return {
        "status": "success",
        "message": result.get("message", "PNR repriced successfully"),
        "pricing": result.get("pricing", {}),
    }


def queue_pnr(request: QueueRequest, query_supplier: Optional[str]) -> Dict[str, Any]:
    svc = resolve_request_service(request, query_supplier, get_booking_snapshot(request.pnr))
    return svc.place_in_queue(request)


# ── Ticketing ────────────────────────────────────────────────────────────────

def _guard_issue_price(svc: Any, request: TicketingRequest, snapshot: Optional[Dict[str, Any]],
                       quote: Dict[str, Any]) -> None:
    """Live fare vs confirmed_total, else vs the booked fare on record (in BDT), else confirmation required."""
    tolerance = supplier_tolerance(svc)
    public_quote = _public_quote(quote)
    if request.confirmed_total is not None:
        assert_charge_confirmed(quote["amount"], quote["currency"], request.confirmed_total, tolerance,
                                request.confirmed_currency, public_quote)
    elif snapshot and snapshot["booked_fare_bdt"] > 0:
        assert_charge_confirmed(to_bdt(quote["amount"], quote["currency"]), "BDT",
                                snapshot["booked_fare_bdt"], tolerance, quote_extra=public_quote)
    else:
        assert_charge_confirmed(quote["amount"], quote["currency"], None, quote_extra=public_quote)


def issue_ticket(request: TicketingRequest, query_supplier: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
    snapshot = get_booking_snapshot(request.pnr)
    svc = resolve_request_service(request, query_supplier, snapshot)

    # 1. Live re-check of the fare, 2. price guard
    quote = svc.quote_issue(
        request.pnr,
        passenger_types=(snapshot or {}).get("passenger_types"),
        validating_carrier=request.validating_carrier,
    )
    try:
        _guard_issue_price(svc, request, snapshot, quote)
    except PriceChangedError:
        svc.release_quote(quote)
        raise

    # 3. Issue
    response = svc.issue_ticket(request, quote)
    formatted = format_ticketing_response(svc.integration_provider, response)

    record_saved = log_ticket(request=request, response=response,
                              supplier_code=svc.supplier_code, user_id=user_id)
    if not record_saved and formatted.get("status") == "success":
        write_log(f"[Ticket] TICKETS NOT RECORDED in DB for PNR {request.pnr}: {formatted}",
                  source="flight.operations.issue_ticket", type="error")

    formatted["price_check"] = _public_quote(quote)
    formatted["record_saved"] = record_saved
    return formatted


def void_ticket(request: VoidTicketRequest, query_supplier: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
    snapshot = get_booking_snapshot(request.pnr)
    svc = resolve_request_service(request, query_supplier, snapshot)
    response = svc.void_ticket(request)

    errors = response.get("errors") if isinstance(response, dict) else None
    if errors:
        return {"status": "error", "message": "Void failed", "errors": errors}

    remaining = [t for t in (snapshot or {}).get("issued_tickets", []) if t != request.ticket_number]
    record_saved = log_ticket_status_change(
        request.pnr, [request.ticket_number], "VOIDED", "VOID",
        user_id=user_id, booking_status=None if remaining else "VOIDED",
    )
    return {"status": "success", "message": f"Ticket {request.ticket_number} voided",
            "record_saved": record_saved, "supplier_response": response}


# ── Exchange (reissue) ───────────────────────────────────────────────────────

def quote_exchange(request: ExchangeQuoteRequest, query_supplier: Optional[str]) -> Dict[str, Any]:
    snapshot = get_booking_snapshot(request.pnr)
    svc = resolve_request_service(request, query_supplier, snapshot)
    passenger_types = request.passenger_types or (snapshot or {}).get("passenger_types")
    quote = svc.quote_exchange(request, passenger_types)
    quote_id = save_quote("exchange", {
        "pnr": request.pnr,
        "original_ticket_number": request.original_ticket_number,
        "supplier_code": svc.supplier_code,
        "new_flight_segments": request.new_flight_segments,
        "passenger_types": passenger_types,
        "amount": quote["amount"],
        "currency": quote["currency"],
    })
    return format_exchange_response(quote, quote_id=quote_id)


def exchange_ticket(request: ExchangeTicketRequest, user_id: Optional[str]) -> Dict[str, Any]:
    saved = load_quote(request.quote_id, "exchange", request.pnr)
    if saved["original_ticket_number"] != request.original_ticket_number:
        raise ValueError("Quote was issued for a different ticket")
    svc = resolve_supplier(saved["supplier_code"])
    tolerance = supplier_tolerance(svc)

    if saved.get("pqr_number"):
        # A previous confirm already changed the itinerary and stored the reissue record at the
        # confirmed price — retry only the reissue, never the exchange itself.
        live = {"amount": saved.get("amount"), "currency": saved.get("currency"), "breakdown": saved.get("breakdown"),
                "context": {"pqr_number": saved["pqr_number"]}}
    else:
        # 1. Live re-check of the exchange price (Travelport keeps its workbench open for the commit)
        live = svc.quote_exchange(
            ExchangeQuoteRequest(
                pnr=request.pnr,
                original_ticket_number=request.original_ticket_number,
                new_flight_segments=saved["new_flight_segments"],
            ),
            saved.get("passenger_types"),
            keep_open=True,
        )
        live["context"] = {**(live.get("context") or {}),
                           "new_flight_segments": saved["new_flight_segments"], "tolerance": float(tolerance)}

        # 2. Price guard
        try:
            assert_charge_confirmed(live["amount"], live["currency"], request.confirmed_amount,
                                    tolerance, request.confirmed_currency, _public_quote(live))
        except PriceChangedError:
            svc.release_quote(live)
            raise

    # 3. Reissue
    try:
        response = svc.exchange_ticket(request, live)
    except PartialExchangeError as exc:
        update_quote(request.quote_id, {"pqr_number": exc.pqr_number, "amount": live["amount"],
                                        "currency": live["currency"], "breakdown": live.get("breakdown")},
                     ttl_minutes=24 * 60)
        log_ticket_status_change(
            request.pnr, [request.original_ticket_number], "ISSUED", "REISSUE_PENDING",
            details={"pqr_number": exc.pqr_number, "error": str(exc)[:500]}, user_id=user_id,
        )
        raise
    consume_quote(request.quote_id)

    new_tickets = [t.get("TicketNumber") for t in response.get("TicketDetails", []) if isinstance(t, dict)]
    log_ticket_status_change(
        request.pnr, [request.original_ticket_number], "EXCHANGED", "REISSUE",
        details={"new_tickets": new_tickets, "amount_collected": live["amount"], "currency": live["currency"],
                 "pqr_number": response.get("pqr_number")},
        user_id=user_id,
    )
    return format_exchange_response(live, response)


# ── Refund ───────────────────────────────────────────────────────────────────

def quote_refund(request: RefundQuoteRequest, query_supplier: Optional[str]) -> Dict[str, Any]:
    svc = resolve_request_service(request, query_supplier, get_booking_snapshot(request.pnr))
    return format_refund_response(svc.quote_refund(request))


def refund_ticket(request: RefundTicketRequest, query_supplier: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
    svc = resolve_request_service(request, query_supplier, get_booking_snapshot(request.pnr))

    # 1. Live re-quote
    live = svc.quote_refund(request)
    if not live["refundable"]:
        reason = live.get("reason") or "not refundable through the API"
        raise ValueError(f"Tickets {request.ticket_numbers} cannot be refunded: {reason}")

    # 2. Price guard
    assert_refund_confirmed(live["amount"], live["currency"], request.confirmed_refund_amount,
                            supplier_tolerance(svc), request.confirmed_currency, _public_quote(live))

    # 3. Refund
    response = svc.refund_ticket(request, live)
    record_saved = log_refund(
        request.pnr, request.ticket_numbers, live["amount"], live["penalty"], live["currency"],
        reason=request.reason, user_id=user_id,
    )
    formatted = format_refund_response(live, response)
    formatted["record_saved"] = record_saved
    return formatted


# ── Ancillaries ──────────────────────────────────────────────────────────────

def seat_map(request: SeatMapRequest, query_supplier: Optional[str]) -> Dict[str, Any]:
    snapshot = get_booking_snapshot(request.pnr) if request.pnr else None
    return resolve_request_service(request, query_supplier, snapshot).get_seat_maps(request)


def baggage_allowance(request: BaggageAllowanceRequest, query_supplier: Optional[str]) -> Dict[str, Any]:
    svc = resolve_request_service(request, query_supplier, get_booking_snapshot(request.pnr))
    return svc.get_baggage_allowance(request)


def fare_rules(request: FareRulesRequest, query_supplier: Optional[str]) -> Dict[str, Any]:
    svc = resolve_request_service(request, query_supplier)
    return format_fare_rules_response(svc.integration_provider, svc.get_fare_rules(request))
