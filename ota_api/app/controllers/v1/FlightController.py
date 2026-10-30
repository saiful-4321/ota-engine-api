from fastapi import APIRouter, BackgroundTasks, Query, Request

from app.models.flight_schemas import (
    FlightSearchRequest, FlightPricingRequest, FlightBookingRequest, TicketingRequest,
    PNRDetailsRequest, CancelItineraryRequest, VoidTicketRequest, ExchangeTicketRequest,
    ExchangeQuoteRequest, RefundQuoteRequest, RefundTicketRequest,
    SeatMapRequest, BaggageAllowanceRequest, QueueRequest, FareRulesRequest,
    RepricePNRRequest,
)
from app.helpers.flight import ALL_SUPPLIERS, operations, handle_errors, run_flight_search
from app.utils.request_utils import get_optional_user_id

# Endpoints are plain `def`: FastAPI runs them in its threadpool, so blocking supplier HTTP calls
# never stall the event loop. Workflows live in app/helpers/flight (search, operations).
router = APIRouter()

_S = Query(
    default=None,
    description=(
        "Supplier code (e.g. 'SABRE-BD-DAC') or provider key (e.g. 'sabre'). Optional: the supplier is "
        "taken from the request body, the booking record (PNR operations) or the flight segments."
    )
)
_SEARCH_S = Query(
    default=ALL_SUPPLIERS,
    description=(
        "'all' (default) searches every active supplier; a provider key ('sabre', 'travelport') searches "
        "that provider's active suppliers; a supplier code ('SABRE-BD-DAC') searches only that supplier."
    )
)


# ===========================================================================
# Search
# ===========================================================================

@router.post(
    "/search",
    summary="Search Flights",
    description=(
        "Supplier-agnostic search. By default (`?supplier=all`) every active supplier is searched in "
        "parallel and results are merged by price. `?supplier=sabre` / `?supplier=travelport` limits the "
        "fan-out to one provider; a supplier code like `?supplier=SABRE-BD-DAC` queries one supplier. "
        "Every search is logged asynchronously to `flight_search_requests_log`."
    )
)
def search_flights(
    request: FlightSearchRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    supplier: str = _SEARCH_S,
):
    return run_flight_search(request, http_request, background_tasks, supplier)


# ===========================================================================
# Pricing
# ===========================================================================

@router.post("/price", summary="Price / Revalidate Itinerary",
             description="Verifies live pricing for a given flight itinerary.")
@handle_errors
def price_flight(request: FlightPricingRequest, supplier: str = _S):
    return operations.price_flight(request, supplier)


# ===========================================================================
# Booking (PNR)
# ===========================================================================

@router.post("/book", summary="Create Booking (PNR)",
             description=(
                 "Creates a passenger name record to lock in the reservation. The booking is recorded at "
                 "the price the supplier stored in the PNR; `price_check` reports any difference from the "
                 "price the client sent."
             ))
@handle_errors
def book_flight(request: FlightBookingRequest, http_request: Request, supplier: str = _S):
    return operations.book(request, supplier, get_optional_user_id(http_request))


@router.post("/pnr/details", summary="Get PNR Details",
             description="Retrieves full details of an existing booking / PNR.")
@handle_errors
def pnr_details(request: PNRDetailsRequest, supplier: str = _S):
    return operations.pnr_details(request, supplier)


@router.post("/pnr/cancel", summary="Cancel Itinerary",
             description=(
                 "Cancels an existing itinerary / PNR. Refused while the PNR has issued tickets — "
                 "void or refund them first, otherwise their value can be lost."
             ))
@handle_errors
def pnr_cancel(request: CancelItineraryRequest, http_request: Request, supplier: str = _S):
    return operations.cancel_pnr(request, supplier, get_optional_user_id(http_request))


@router.post(
    "/pnr/reprice",
    summary="Reprice PNR",
    description=(
        "Re-prices the itinerary on an existing PNR (Sabre: live reprice, stores a fresh price quote; "
        "Travelport: stored fare, re-validated at ticketing). Returns the fare for customer confirmation."
    )
)
@handle_errors
def pnr_reprice(request: RepricePNRRequest, supplier: str = _S):
    return operations.reprice_pnr(request, supplier)


@router.post("/pnr/queue", summary="Place PNR on Queue",
             description="Places a PNR on a specific agency queue.")
@handle_errors
def queue_place(request: QueueRequest, supplier: str = _S):
    return operations.queue_pnr(request, supplier)


# ===========================================================================
# Ticketing
# ===========================================================================

@router.post("/ticket/issue", summary="Issue Flight Ticket",
             description=(
                 "Issues electronic tickets for a PNR. The fare is re-checked with the supplier first; if it "
                 "is higher than `confirmed_total` (or the booked fare when omitted), nothing is issued and "
                 "HTTP 409 returns the new price for the customer to accept."
             ))
@handle_errors
def ticket_issue(request: TicketingRequest, http_request: Request, supplier: str = _S):
    return operations.issue_ticket(request, supplier, get_optional_user_id(http_request))


@router.post("/ticket/void", summary="Void Flight Ticket",
             description="Voids a previously issued electronic ticket (typically same day as issue).")
@handle_errors
def ticket_void(request: VoidTicketRequest, http_request: Request, supplier: str = _S):
    return operations.void_ticket(request, supplier, get_optional_user_id(http_request))


@router.post("/ticket/exchange/quote", summary="Quote Ticket Exchange (Reissue)",
             description=(
                 "Prices an exchange of an issued ticket to new flights without changing anything. Returns the "
                 "amount to collect and a `quote_id` for /ticket/exchange."
             ))
@handle_errors
def ticket_exchange_quote(request: ExchangeQuoteRequest, supplier: str = _S):
    return operations.quote_exchange(request, supplier)


@router.post("/ticket/exchange", summary="Exchange Ticket (Reissue)",
             description=(
                 "Reissues the ticket priced by /ticket/exchange/quote. The exchange is re-priced live first; "
                 "if the amount to collect is higher than `confirmed_amount`, nothing is submitted and "
                 "HTTP 409 returns the new amount."
             ))
@handle_errors
def ticket_exchange(request: ExchangeTicketRequest, http_request: Request):
    return operations.exchange_ticket(request, get_optional_user_id(http_request))


@router.post("/ticket/refund/quote", summary="Quote Ticket Refund",
             description="Prices a refund (refundable amount and penalty) without changing anything.")
@handle_errors
def ticket_refund_quote(request: RefundQuoteRequest, supplier: str = _S):
    return operations.quote_refund(request, supplier)


@router.post("/ticket/refund", summary="Refund Ticket",
             description=(
                 "Refunds tickets. The refund is re-quoted live first; if the refundable amount is lower than "
                 "`confirmed_refund_amount`, nothing is submitted and HTTP 409 returns the new amount."
             ))
@handle_errors
def ticket_refund(request: RefundTicketRequest, http_request: Request, supplier: str = _S):
    return operations.refund_ticket(request, supplier, get_optional_user_id(http_request))


# ===========================================================================
# Ancillaries
# ===========================================================================

@router.post("/seats/map", summary="Get Seat Map",
             description="Retrieves available seats for a specific flight segment.")
@handle_errors
def seat_map(request: SeatMapRequest, supplier: str = _S):
    return operations.seat_map(request, supplier)


@router.post(
    "/baggage/allowance",
    summary="Get Baggage Allowance",
    description="Checks baggage allowance for a given PNR."
)
@handle_errors
def baggage_allowance(request: BaggageAllowanceRequest, supplier: str = _S):
    return operations.baggage_allowance(request, supplier)


@router.post(
    "/fare/rules",
    summary="Get Fare Rules",
    description="Retrieves structured fare rules for a given flight segment."
)
@handle_errors
def fare_rules(request: FareRulesRequest, supplier: str = _S):
    return operations.fare_rules(request, supplier)
