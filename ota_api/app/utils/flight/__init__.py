from typing import Any, Dict, List

from app.utils.flight import baggage, fare_rules, sabre, seat_maps, travelport
# from app.utils.flight import amadeus   # ← future

# Every formatter is dispatched on the supplier's `integration_provider` ('sabre', 'travelport'),
# never on the supplier code — codes are free text set by admins (e.g. 'SKY-DAC-01').


def _provider(supplier: str) -> str:
    return str(supplier or "").strip().lower()


# ---------------------------------------------------------------------------
# Shared: error envelope (supplier-independent)
# ---------------------------------------------------------------------------
def format_error_response(error: Exception) -> Dict[str, Any]:
    return sabre.format_error_response(error)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def format_search_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = _provider(supplier)
    if key == "sabre":
        return sabre.format_bfm_response(response)
    if key == "travelport":
        return travelport.format_catalog_search_response(response)
    return response


def build_search_filters(flights: List[Dict[str, Any]]) -> Dict[str, Any]:
    return sabre.build_filters(flights)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
def format_pricing_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = _provider(supplier)
    if key == "sabre":
        return sabre.format_pricing_response(response)
    if key == "travelport":
        return travelport.format_pricing_response(response)
    return response


# ---------------------------------------------------------------------------
# PNR / AtBooking
# ---------------------------------------------------------------------------
def format_pnr_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = _provider(supplier)
    if key == "sabre":
        return sabre.format_pnr_response(response)
    if key == "travelport":
        return travelport.format_pnr_response(response)
    return response


def format_pnr_details_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = _provider(supplier)
    if key == "sabre":
        return sabre.format_pnr_details_response(response)
    if key == "travelport":
        return travelport.format_pnr_response(response)
    return response


def format_cancel_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = _provider(supplier)
    if key == "sabre":
        return sabre.format_cancel_response(response)
    if key == "travelport":
        return travelport.format_cancel_response(response)
    return response


# ---------------------------------------------------------------------------
# Ticketing
# ---------------------------------------------------------------------------
def format_ticketing_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = _provider(supplier)
    if key == "sabre":
        return sabre.format_ticketing_response(response)
    if key == "travelport":
        return travelport.format_ticketing_response(response)
    return response


def format_refund_response(quote: Dict[str, Any], response: Dict[str, Any] = None) -> Dict[str, Any]:
    """Provider-independent: services already return normalized refund quotes."""
    body = {
        "refundable": quote.get("refundable"),
        "refund_amount": quote.get("amount"),
        "penalty": quote.get("penalty"),
        "currency": quote.get("currency"),
        "tickets": quote.get("tickets"),
        "reason": quote.get("reason"),
    }
    if response is None:
        return {"status": "success", "message": "Refund quote", "refund": body}
    return {"status": "success", "message": "Refund submitted", "refund": {**body, "supplier_status": response.get("refund_status")}}


def format_exchange_response(quote: Dict[str, Any], response: Dict[str, Any] = None, quote_id: str = None) -> Dict[str, Any]:
    body = {
        "amount_due": quote.get("amount"),
        "currency": quote.get("currency"),
        "breakdown": quote.get("breakdown"),
    }
    if response is None:
        return {"status": "success", "message": "Exchange quote", "exchange": {**body, "quote_id": quote_id}}
    tickets = [t.get("TicketNumber") for t in response.get("TicketDetails", []) if isinstance(t, dict)]
    return {"status": "success", "message": "Ticket exchanged", "exchange": {**body, "new_ticket_numbers": tickets}}


# ---------------------------------------------------------------------------
# Ancillaries: seat map, baggage, fare rules (one shape for every supplier)
# ---------------------------------------------------------------------------
def format_seat_map_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = _provider(supplier)
    if key == "sabre":
        return {"status": "success", **seat_maps.from_sabre(response)}
    if key == "travelport":
        return {"status": "success", **seat_maps.from_travelport(response)}
    return response


def format_baggage_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = _provider(supplier)
    if key == "sabre":
        return {"status": "success", **baggage.from_sabre(response)}
    if key == "travelport":
        return {"status": "success", **baggage.from_travelport(response)}
    return response


def format_fare_rules_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sabre: `response` is the getBooking body.
    Travelport: `response` is {"structured": FareRuleListResponse, "text": FareRuleListResponse | None}.
    """
    key = _provider(supplier)
    if key == "sabre":
        return {"status": "success", **fare_rules.from_sabre_booking(response)}
    if key == "travelport":
        return {"status": "success", **fare_rules.from_travelport(response["structured"], response.get("text"))}
    return response
