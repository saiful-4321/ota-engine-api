from typing import Any, Dict

from app.utils.flight import sabre
# from app.utils.flight import amadeus   # ← future


# ---------------------------------------------------------------------------
# Shared: error envelope (supplier-independent)
# ---------------------------------------------------------------------------
def format_error_response(error: Exception) -> Dict[str, Any]:
    return sabre.format_error_response(error)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def format_search_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    if supplier == "sabre":
        return sabre.format_bfm_response(response)
    # elif supplier == "amadeus":
    #     return amadeus.format_search_response(response)
    return response


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
def format_pricing_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    if supplier == "sabre":
        return sabre.format_pricing_response(response)
    return response


# ---------------------------------------------------------------------------
# PNR / Booking
# ---------------------------------------------------------------------------
def format_pnr_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    if supplier == "sabre":
        return sabre.format_pnr_response(response)
    return response


def format_pnr_details_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    if supplier == "sabre":
        return sabre.format_pnr_details_response(response)
    return response


def format_cancel_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    if supplier == "sabre":
        return sabre.format_cancel_response(response)
    return response


# ---------------------------------------------------------------------------
# Ticketing
# ---------------------------------------------------------------------------
def format_ticketing_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    if supplier == "sabre":
        return sabre.format_ticketing_response(response)
    return response


# ---------------------------------------------------------------------------
# Fare Rules
# ---------------------------------------------------------------------------
def format_fare_rules_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    if supplier == "sabre":
        return sabre.format_fare_rules_response(response)
    return response
