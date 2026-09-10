import uuid
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse

from app.models.flight_schemas import (
    FlightSearchRequest, FlightPricingRequest, FlightBookingRequest, TicketingRequest,
    PNRDetailsRequest, CancelItineraryRequest, VoidTicketRequest, ExchangeTicketRequest,
    SeatMapRequest, BaggageAllowanceRequest, QueueRequest, FareRulesRequest,
    RepricePNRRequest,
)
from app.helpers.flight import (
    DEFAULT_SUPPLIER, resolve_supplier, get_active_flight_suppliers,
    log_search_request, log_booking, log_ticket,
    format_error_response, format_search_response, format_pricing_response,
    format_pnr_response, format_pnr_details_response, format_cancel_response,
    format_ticketing_response, format_fare_rules_response,
    build_search_filters,
)
from app.helpers.common import get_client_ip, get_optional_user_id

router = APIRouter()

_S = Query(
    default=DEFAULT_SUPPLIER,
    description="Supplier provider key (e.g. 'sabre') or specific supplier code (e.g. 'SABRE-BD-DAC'). Defaults to active supplier."
)


def _get_provider_title(integration_provider: str) -> str:
    prov = str(integration_provider or "").lower()
    if "travelport" in prov or "galileo" in prov:
        return "Travelport"
    elif "sabre" in prov:
        return "Sabre"
    elif "amadeus" in prov:
        return "Amadeus"
    return integration_provider.title() if integration_provider else "Sabre"


def _tag_flight_with_supplier(flight: Dict[str, Any], sup_cfg: Any) -> None:
    """Enriches each flight dictionary with supplier metadata and NDC tags."""
    prov_title = _get_provider_title(sup_cfg.integration_provider)
    flight["supplier_code"] = sup_cfg.supplier_code
    flight["supplier"]      = sup_cfg.supplier_code
    flight["supplier_name"] = sup_cfg.supplier_name
    flight["apiProvider"]   = prov_title
    flight["api_provider"]  = sup_cfg.integration_provider
    flight["pcc"]           = sup_cfg.pcc

    # Determine NDC fare: from provider payload OR supplier configuration
    sup_type = str(getattr(sup_cfg, "supplier_type", "") or "").upper()
    sup_code = str(getattr(sup_cfg, "supplier_code", "") or "").lower()
    sup_name = str(getattr(sup_cfg, "supplier_name", "") or "").lower()
    is_ndc_supplier = (sup_type == "NDC" or "ndc" in sup_code or "ndc" in sup_name)

    is_ndc = bool(flight.get("isNdc") or flight.get("is_ndc") or is_ndc_supplier)
    flight["isNdc"]          = is_ndc
    flight["is_ndc"]         = is_ndc
    flight["fareType"]       = "NDC" if is_ndc else flight.get("fareType", "GDS")
    flight["fare_type"]      = flight["fareType"]
    flight["contentSource"]  = "NDC" if is_ndc else flight.get("contentSource", "GDS")

    tags = list(flight.get("tags") or [])
    if is_ndc and "NDC" not in tags:
        tags.append("NDC")
    flight["tags"] = tags


# ===========================================================================
# Search
# ===========================================================================

@router.post(
    "/search",
    summary="Search Flights",
    description=(
        "Supplier-agnostic search. Pass `?supplier=sabre` (default) to fan-out to ALL active suppliers "
        "and get results merged by price. Pass a specific code like `?supplier=SABRE-BD-DAC` to query "
        "one supplier only. Every search is logged asynchronously to `flight_search_requests_log`."
    )
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

    # ── Determine whether to fan-out to ALL suppliers or use one ─────────────
    # Fan-out when the caller passes the generic provider key (e.g. 'sabre') or
    # the default alias. A specific supplier code (e.g. 'SABRE-BD-DAC') targets
    # exactly that supplier.
    ident           = str(supplier or DEFAULT_SUPPLIER).strip().lower()
    is_specific_sup = "-" in ident  # e.g. 'sabre-bd-dac' vs 'sabre'

    try:
        t_supplier_start = time.monotonic()

        if is_specific_sup:
            # ── Single-supplier mode ──────────────────────────────────────────
            svc          = resolve_supplier(supplier)
            raw_response = svc.search_flights(request)
            provider     = getattr(svc, "integration_provider", supplier)
            formatted    = format_search_response(provider, raw_response)
            supplier_ms  = int((time.monotonic() - t_supplier_start) * 1000)

            # Tag flights with actual supplier details and NDC markers
            if formatted and isinstance(formatted.get("flights"), list):
                sup_cfg = svc.config
                for flight in formatted["flights"]:
                    _tag_flight_with_supplier(flight, sup_cfg)
                formatted["filters"] = build_search_filters(formatted["flights"])
        else:
            # ── Multi-supplier fan-out mode ───────────────────────────────────
            # Load all active suppliers for this integration_provider / service.
            active_suppliers: Dict[str, Any] = get_active_flight_suppliers(service="flight")

            if not active_suppliers:
                # Fallback: no active suppliers found — try the generic key
                svc          = resolve_supplier(supplier)
                raw_response = svc.search_flights(request)
                provider     = getattr(svc, "integration_provider", supplier)
                formatted    = format_search_response(provider, raw_response)
                supplier_ms  = int((time.monotonic() - t_supplier_start) * 1000)

                # Tag flights with actual supplier details and NDC markers
                if formatted and isinstance(formatted.get("flights"), list):
                    sup_cfg = svc.config
                    for flight in formatted["flights"]:
                        _tag_flight_with_supplier(flight, sup_cfg)
                    formatted["filters"] = build_search_filters(formatted["flights"])
            else:
                # Run all supplier calls concurrently in a thread pool
                loop = asyncio.get_event_loop()

                def _call_supplier(code_svc):
                    code, svc = code_svc
                    try:
                        raw  = svc.search_flights(request)
                        prov = getattr(svc, "integration_provider", code)
                        fmt  = format_search_response(prov, raw)
                        return code, fmt, None
                    except Exception as exc:
                        return code, None, str(exc)

                with ThreadPoolExecutor(max_workers=len(active_suppliers)) as pool:
                    tasks   = list(active_suppliers.items())
                    results = await loop.run_in_executor(
                        pool,
                        lambda: [_call_supplier(t) for t in tasks]
                    )

                supplier_ms = int((time.monotonic() - t_supplier_start) * 1000)

                # ── Merge all supplier flight lists ───────────────────────────
                merged_flights: List[Dict[str, Any]] = []
                supplier_metadata: Dict[str, Any]   = {}
                errors_by_supplier: Dict[str, str]  = {}

                for code, fmt, err in results:
                    if err:
                        errors_by_supplier[code] = err
                        print(f"[Search] Supplier '{code}' failed: {err}", flush=True)
                        continue
                    if fmt and isinstance(fmt.get("flights"), list):
                        sup_cfg = active_suppliers[code].config
                        # Tag each flight with its originating supplier details and NDC markers
                        for flight in fmt["flights"]:
                            _tag_flight_with_supplier(flight, sup_cfg)
                        merged_flights.extend(fmt["flights"])
                        supplier_metadata[code] = fmt.get("metadata", {})

                # Sort merged results by numeric price ascending
                merged_flights.sort(key=lambda f: f.get("numericPrice") or f.get("price", {}).get("total") or 0)

                # Build filters from the full merged flight set
                merged_filters = build_search_filters(merged_flights)

                # Build unified metadata
                formatted = {
                    "status":  "success" if merged_flights else "no_results",
                    "message": "Flights found" if merged_flights else "No flights found across any supplier.",
                    "metadata": {
                        "total_results":       len(merged_flights),
                        "suppliers_queried":   list(active_suppliers.keys()),
                        "suppliers_succeeded": [c for c in active_suppliers if c not in errors_by_supplier],
                        "suppliers_failed":    errors_by_supplier,
                        "per_supplier":        supplier_metadata,
                    },
                    "filters": merged_filters,
                    "flights": merged_flights,
                }

        api_ms = int((time.monotonic() - t_start) * 1000)

        timing_metadata = {
            "supplier_response_time_ms": supplier_ms,
            "api_response_time_ms":      api_ms,
            "ip_address":                ip_address,
            "user_agent":                user_agent
        }

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
        sup = getattr(request, "supplier", None) or supplier
        return format_pricing_response(sup, resolve_supplier(sup).price_flight(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


# ===========================================================================
# AtBooking (PNR)
# ===========================================================================

@router.post("/book", summary="Create Booking (PNR)",
             description="Creates a passenger name record to lock in the reservation.")
async def book_flight(
    request: FlightBookingRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    supplier: str = _S
):
    try:
        sup = getattr(request, "supplier", None) or supplier
        response = resolve_supplier(sup).create_pnr(request)
        formatted = format_pnr_response(sup, response)
        
        # Log successful booking
        background_tasks.add_task(
            log_booking,
            request = request,
            response = response,
            supplier_code = sup,
            user_id = get_optional_user_id(http_request)
        )
        
        return formatted
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/pnr/details", summary="Get PNR Details",
             description="Retrieves full details of an existing booking / PNR.")
async def pnr_details(request: PNRDetailsRequest, supplier: str = _S):
    try:
        sup = getattr(request, "supplier", None) or supplier
        return format_pnr_details_response(sup, resolve_supplier(sup).get_pnr_details(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/pnr/cancel", summary="Cancel Itinerary",
             description="Cancels an existing itinerary / PNR.")
async def pnr_cancel(request: CancelItineraryRequest, supplier: str = _S):
    try:
        sup = getattr(request, "supplier", None) or supplier
        return format_cancel_response(sup, resolve_supplier(sup).cancel_itinerary(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post(
    "/pnr/reprice",
    summary="Reprice PNR",
    description=(
        "Regenerates the price quote on an existing PNR. "
        "Call this when the original price quote has expired (Sabre error 1496). "
        "Returns the fresh pricing for user confirmation before re-issuing."
    )
)
async def pnr_reprice(request: RepricePNRRequest, supplier: str = _S):
    try:
        sup = getattr(request, "supplier", None) or supplier
        result = resolve_supplier(sup).reprice_pnr(
            pnr=request.pnr,
            passenger_types=request.passenger_types,
            validating_carrier=getattr(request, "validating_carrier", None),
        )
        return {
            "status": "success",
            "message": result.get("message", "PNR repriced successfully"),
            "pricing": result.get("pricing", {}),
        }
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/pnr/queue", summary="Place PNR on Queue",
             description="Places a PNR on a specific agency queue.")
async def queue_place(request: QueueRequest, supplier: str = _S):
    try:
        sup = getattr(request, "supplier", None) or supplier
        return resolve_supplier(sup).place_in_queue(request)
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


# ===========================================================================
# Ticketing
# ===========================================================================

@router.post("/ticket/issue", summary="Issue AtFlightTicket",
             description="Issues an electronic air ticket for a reservation (PNR).")
async def ticket_issue(
    request: TicketingRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    supplier: str = _S
):
    try:
        sup = getattr(request, "supplier", None) or supplier
        response = resolve_supplier(sup).issue_ticket(request)
        formatted = format_ticketing_response(sup, response)
        
        # Log ticket issuance as a background task to prevent blocking or failing the API response
        # if the database transaction encounters an error after the supplier has already issued the ticket.
        background_tasks.add_task(
            log_ticket,
            request = request,
            response = response,
            supplier_code = sup,
            user_id = get_optional_user_id(http_request)
        )
        
        return formatted
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/ticket/void", summary="Void AtFlightTicket",
             description="Voids a previously issued electronic ticket (typically within 24 hours).")
async def ticket_void(request: VoidTicketRequest, supplier: str = _S):
    try:
        sup = getattr(request, "supplier", None) or supplier
        return resolve_supplier(sup).void_ticket(request)
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))


@router.post("/ticket/exchange", summary="Exchange AtFlightTicket (Auto Reissue)",
             description="Performs an automated exchange / reissue of an existing ticket.")
async def ticket_exchange(request: ExchangeTicketRequest, supplier: str = _S):
    try:
        sup = getattr(request, "supplier", None) or supplier
        return resolve_supplier(sup).exchange_ticket(request)
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
        sup = getattr(request, "supplier", None) or supplier
        return resolve_supplier(sup).get_seat_maps(request)
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
        sup = getattr(request, "supplier", None) or supplier
        return resolve_supplier(sup).get_baggage_allowance(request)
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
        sup = getattr(request, "supplier", None) or supplier
        return format_fare_rules_response(sup, resolve_supplier(sup).get_fare_rules(request))
    except ValueError as ve:
        return JSONResponse(status_code=400, content=format_error_response(ve))
    except Exception as e:
        return JSONResponse(status_code=400, content=format_error_response(e))
