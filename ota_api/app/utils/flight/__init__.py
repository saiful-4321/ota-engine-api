from typing import Any, Dict, List

from app.utils.flight import sabre, travelport
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
    key = str(supplier or "").lower()
    if "sabre" in key:
        return sabre.format_bfm_response(response)
    elif "travelport" in key or "gal" in key or (isinstance(response, dict) and "CatalogProductOfferingsResponse" in response):
        return travelport.format_catalog_search_response(response)
    # elif "amadeus" in key:
    #     return amadeus.format_search_response(response)
    return response


def build_search_filters(flights: List[Dict[str, Any]]) -> Dict[str, Any]:
    return sabre.build_filters(flights)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
def format_pricing_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = str(supplier or "").lower()
    if "sabre" in key:
        return sabre.format_pricing_response(response)
    return response


# ---------------------------------------------------------------------------
# PNR / AtBooking
# ---------------------------------------------------------------------------
def format_pnr_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = str(supplier or "").lower()
    if "sabre" in key:
        return sabre.format_pnr_response(response)
    return response


def format_pnr_details_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = str(supplier or "").lower()
    if "sabre" in key:
        return sabre.format_pnr_details_response(response)
    return response


def format_cancel_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = str(supplier or "").lower()
    if "sabre" in key:
        return sabre.format_cancel_response(response)
    return response


# ---------------------------------------------------------------------------
# Ticketing
# ---------------------------------------------------------------------------
def format_ticketing_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = str(supplier or "").lower()
    if "sabre" in key:
        return sabre.format_ticketing_response(response)
    return response


# ---------------------------------------------------------------------------
# Fare Rules
# ---------------------------------------------------------------------------
def format_fare_rules_response(supplier: str, response: Dict[str, Any]) -> Dict[str, Any]:
    key = str(supplier or "").lower()
    if "sabre" in key:
        return sabre.format_fare_rules_response(response)
    return response

