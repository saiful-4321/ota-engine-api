import uuid
import time
from typing import Dict, Any

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse

from app.models.sabre_schemas import (
    FlightSearchRequest, FlightPricingRequest, FlightBookingRequest, TicketingRequest,
    PNRDetailsRequest, CancelItineraryRequest, VoidTicketRequest, ExchangeTicketRequest,
    SeatMapRequest, BaggageAllowanceRequest, QueueRequest, FareRulesRequest,
)
from app.helpers.flight import (
    DEFAULT_SUPPLIER, resolve_supplier, log_search_request,
    format_error_response, format_search_response, format_pricing_response,
    format_pnr_response, format_pnr_details_response, format_cancel_response,
    format_ticketing_response, format_fare_rules_response,
)
from app.helpers.common import get_client_ip, get_optional_user_id

router = APIRouter()

_S = Query(default=DEFAULT_SUPPLIER, description="Supplier key, e.g. 'sabre'")


# ===========================================================================
# Search
# ===========================================================================

@router.post(
    "/search",
    summary="Search Flights",
    description="Supplier-agnostic search. Pass `?supplier=sabre` (default). "
    "Every search is logged asynchronously to `flight_search_requests_log`."
)
async def search_flights(
    request: FlightSearchRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    supplier: str = _S,
) -> Dict[str, Any]:
    search_id    = str(uuid.uuid4())
    t_start      = time.monotonic()
    result_count = None
    ip_address   = get_client_ip(http_request)
    user_agent   = http_request.headers.get("user-agent", "")[:500]
    
    try:
        # ── Supplier call (timed independently) ──────────────────────────
        t_supplier_start = time.monotonic()
        raw_response     = resolve_supplier(supplier).search_flights(request)
        supplier_ms      = int((time.monotonic() - t_supplier_start) * 1000)

        # ── Format response ───────────────────────────────────────────────
        formatted = format_search_response(supplier, raw_response)
        api_ms    = int((time.monotonic() - t_start) * 1000)

        # Build timing metadata dict
        timing_metadata = {
            "supplier_response_time_ms": supplier_ms,
            "api_response_time_ms":      api_ms,
            "ip_address":                ip_address,
            "user_agent":                user_agent
        }

        # Extract result count and inject search_id + timing into the response
        if isinstance(formatted, dict):
            result_count = formatted.get("metadata", {}).get("total_results")
            formatted.setdefault("metadata", {})
            formatted["metadata"]["search_id"] = search_id
            formatted["metadata"].update(timing_metadata)

        background_tasks.add_task(
            log_search_request,
            request      = request,
            supplier     = supplier,
            user_id      = get_optional_user_id(http_request),
            session_id   = http_request.headers.get("x-session-id"),
            search_id    = search_id,
            result_count = result_count,
            metadata     = timing_metadata,
            status       = "success",
        )
        return formatted
    except ValueError as ve:
        background_tasks.add_task(
            log_search_request,
            request=request, supplier=supplier,
            user_id=get_optional_user_id(http_request),
            session_id=http_request.headers.get("x-session-id"),
            search_id=search_id,
            metadata={
                "api_response_time_ms": int((time.monotonic() - t_start) * 1000),
                "ip_address": ip_address,
                "user_agent": user_agent
            },
            status="error",
        )
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        background_tasks.add_task(
            log_search_request,
            request=request, supplier=supplier,
            user_id=get_optional_user_id(http_request),
            session_id=http_request.headers.get("x-session-id"),
            search_id=search_id,
            metadata={
                "api_response_time_ms": int((time.monotonic() - t_start) * 1000),
                "ip_address": ip_address,
                "user_agent": user_agent
            },
            status="error",
        )
        return JSONResponse(status_code=400, content=format_error_response(e))


# ===========================================================================
# Pricing
# ===========================================================================

@router.post("/price", summary="Price / Revalidate Itinerary",
             description="Verifies live pricing for a given flight itinerary.")
async def price_flight(request: FlightPricingRequest, supplier: str = _S):
    try:
        return format_pricing_response(supplier, resolve_supplier(supplier).price_flight(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


# ===========================================================================
# Booking (PNR)
# ===========================================================================

@router.post("/book", summary="Create Booking (PNR)",
             description="Creates a passenger name record to lock in the reservation.")
async def book_flight(request: FlightBookingRequest, supplier: str = _S):
    try:
        return format_pnr_response(supplier, resolve_supplier(supplier).create_pnr(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/pnr/details", summary="Get PNR Details",
             description="Retrieves full details of an existing booking / PNR.")
async def pnr_details(request: PNRDetailsRequest, supplier: str = _S):
    try:
        return format_pnr_details_response(supplier, resolve_supplier(supplier).get_pnr_details(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/pnr/cancel", summary="Cancel Itinerary",
             description="Cancels an existing itinerary / PNR.")
async def pnr_cancel(request: CancelItineraryRequest, supplier: str = _S):
    try:
        return format_cancel_response(supplier, resolve_supplier(supplier).cancel_itinerary(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/pnr/queue", summary="Place PNR on Queue",
             description="Places a PNR on a specific agency queue.")
async def queue_place(request: QueueRequest, supplier: str = _S):
    try:
        return resolve_supplier(supplier).place_in_queue(request)
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


# ===========================================================================
# Ticketing
# ===========================================================================

@router.post("/ticket/issue", summary="Issue Ticket",
             description="Issues an electronic air ticket for a reservation (PNR).")
async def ticket_issue(request: TicketingRequest, supplier: str = _S):
    try:
        return format_ticketing_response(supplier, resolve_supplier(supplier).issue_ticket(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/ticket/void", summary="Void Ticket",
             description="Voids a previously issued electronic ticket (typically within 24 hours).")
async def ticket_void(request: VoidTicketRequest, supplier: str = _S):
    try:
        return resolve_supplier(supplier).void_ticket(request)
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/ticket/exchange", summary="Exchange Ticket (Auto Reissue)",
             description="Performs an automated exchange / reissue of an existing ticket.")
async def ticket_exchange(request: ExchangeTicketRequest, supplier: str = _S):
    try:
        return resolve_supplier(supplier).exchange_ticket(request)
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


# ===========================================================================
# Ancillaries
# ===========================================================================

@router.post("/seats/map", summary="Get Seat Map",
             description="Retrieves available seats for a specific flight segment.")
async def seat_map(request: SeatMapRequest, supplier: str = _S):
    try:
        return resolve_supplier(supplier).get_seat_maps(request)
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post(
    "/baggage/allowance", 
    summary="Get Baggage Allowance",
    description="Checks baggage allowance for a given PNR."
)
async def baggage_allowance(request: BaggageAllowanceRequest, supplier: str = _S):
    try:
        return resolve_supplier(supplier).get_baggage_allowance(request)
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post(
    "/fare/rules",
    summary="Get Fare Rules",
    description="Retrieves structured fare rules for a given flight segment."
)
async def fare_rules(request: FareRulesRequest, supplier: str = _S):
    try:
        return format_fare_rules_response(supplier, resolve_supplier(supplier).get_fare_rules(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))
