"""
app/helpers/flight/search.py

Supplier fan-out search: runs every selected supplier in parallel, tags each flight (and its
segments) with the supplier that returned it, merges the results by price and logs the search.
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Request

from app.helpers.common import write_log
from app.utils.request_utils import get_client_ip, get_optional_user_id
from app.utils.flight.errors import SupplierError
from app.helpers.flight.logger import log_search_request
from app.helpers.flight.registry import (
    ALL_SUPPLIERS, DEFAULT_SUPPLIER, get_active_flight_suppliers, is_provider_key, resolve_supplier,
)
from app.helpers.flight.responses import error_response
from app.models.flight_schemas import FlightSearchRequest
from app.utils.flight import build_search_filters, format_search_response

SEARCH_TIMEOUT_SECONDS = 75
_search_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="flight-search")


# ── Supplier tagging ─────────────────────────────────────────────────────────

def _get_provider_title(integration_provider: str) -> str:
    prov = str(integration_provider or "").lower()
    if "travelport" in prov or "galileo" in prov:
        return "Travelport"
    elif "sabre" in prov:
        return "Sabre"
    elif "amadeus" in prov:
        return "Amadeus"
    return integration_provider.title() if integration_provider else "Sabre"


def _tag_segments(flight: Dict[str, Any], supplier_code: str) -> None:
    """Segments carry the supplier code too, so /price and /book route to the PCC that returned the fare."""
    for leg in flight.get("legs") or []:
        if not isinstance(leg, dict):
            continue
        for seg in leg.get("segments") or []:
            if isinstance(seg, dict):
                seg["supplier_code"] = supplier_code


def tag_flight_with_supplier(flight: Dict[str, Any], sup_cfg: Any) -> None:
    """Enriches each flight (and its segments) with supplier metadata and NDC tags."""
    prov_title = _get_provider_title(sup_cfg.integration_provider)
    flight["supplier_code"] = sup_cfg.supplier_code
    flight["supplier"]      = sup_cfg.supplier_code
    flight["supplier_name"] = sup_cfg.supplier_name
    flight["apiProvider"]   = prov_title
    flight["api_provider"]  = sup_cfg.integration_provider
    flight["pcc"]           = sup_cfg.pcc

    _tag_segments(flight, sup_cfg.supplier_code)

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


# ── Fan-out ──────────────────────────────────────────────────────────────────

def _price_key(flight: Dict[str, Any]) -> float:
    price = flight.get("price")
    for val in (flight.get("numericPrice"), price.get("total") if isinstance(price, dict) else None):
        try:
            if val is not None:
                return float(val)
        except (TypeError, ValueError):
            continue
    return float("inf")


def _search_one(svc: Any, request: FlightSearchRequest) -> Dict[str, Any]:
    raw = svc.search_flights(request)
    formatted = format_search_response(svc.integration_provider, raw)
    if not isinstance(formatted, dict):
        raise SupplierError(f"Unexpected search response from {svc.supplier_code}")
    for flight in formatted.get("flights") or []:
        tag_flight_with_supplier(flight, svc.config)
    return formatted


def _collect_search_results(futures: Dict[str, Any], not_done: set):
    merged_flights: List[Dict[str, Any]] = []
    supplier_metadata: Dict[str, Any] = {}
    errors_by_supplier: Dict[str, str] = {}
    first_error: Optional[Exception] = None

    for code, fut in futures.items():
        if fut in not_done:
            fut.cancel()
            errors_by_supplier[code] = f"timed out after {SEARCH_TIMEOUT_SECONDS}s"
            continue
        try:
            fmt = fut.result()
        except Exception as exc:
            first_error = first_error or exc
            errors_by_supplier[code] = str(exc)
            write_log(f"[Search] Supplier '{code}' failed: {exc}", source="flight.search", type="warning")
            continue
        merged_flights.extend(fmt.get("flights") or [])
        supplier_metadata[code] = fmt.get("metadata", {})
    return merged_flights, supplier_metadata, errors_by_supplier, first_error


def _suppliers_for_search(supplier: str) -> Dict[str, Any]:
    ident = str(supplier or ALL_SUPPLIERS).strip()
    if ident.lower() == ALL_SUPPLIERS:
        suppliers = get_active_flight_suppliers(service="flight")
    elif is_provider_key(ident):
        suppliers = get_active_flight_suppliers(service="flight", provider=ident)
    else:
        svc = resolve_supplier(ident)
        return {svc.supplier_code: svc}
    if not suppliers:
        # No supplier links configured — fall back to the provider's default supplier
        svc = resolve_supplier(DEFAULT_SUPPLIER if ident.lower() == ALL_SUPPLIERS else ident)
        suppliers = {svc.supplier_code: svc}
    return suppliers


def _fan_out(request: FlightSearchRequest, supplier: str) -> Dict[str, Any]:
    suppliers = _suppliers_for_search(supplier)
    t_start = time.monotonic()
    futures = {code: _search_pool.submit(_search_one, svc, request) for code, svc in suppliers.items()}
    _, not_done = wait(futures.values(), timeout=SEARCH_TIMEOUT_SECONDS)
    supplier_ms = int((time.monotonic() - t_start) * 1000)

    merged_flights, supplier_metadata, errors_by_supplier, first_error = _collect_search_results(futures, not_done)

    if errors_by_supplier and len(errors_by_supplier) == len(futures):
        # Every supplier failed — this is an outage, not "no flights"
        if len(futures) == 1 and first_error is not None:
            raise first_error
        raise SupplierError(f"All suppliers failed: {errors_by_supplier}")

    # Note: suppliers may price in different currencies; ordering assumes a common currency.
    merged_flights.sort(key=_price_key)

    return {
        "status":  "success" if merged_flights else "no_results",
        "message": "Flights found" if merged_flights else "No flights found across any supplier.",
        "metadata": {
            "total_results":             len(merged_flights),
            "suppliers_queried":         list(suppliers.keys()),
            "suppliers_succeeded":       [c for c in suppliers if c not in errors_by_supplier],
            "suppliers_failed":          errors_by_supplier,
            "per_supplier":              supplier_metadata,
            "supplier_response_time_ms": supplier_ms,
        },
        "filters": build_search_filters(merged_flights),
        "flights": merged_flights,
    }


def run_flight_search(
    request: FlightSearchRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    supplier: str,
):
    """Runs the search and schedules the search log. Returns the response body or a JSON error response."""
    search_id  = str(uuid.uuid4())
    t_start    = time.monotonic()
    client_meta = {
        "ip_address": get_client_ip(http_request),
        "user_agent": http_request.headers.get("user-agent", "")[:500],
    }
    log_kwargs = {
        "request": request,
        "user_id": get_optional_user_id(http_request),
        "session_id": http_request.headers.get("x-session-id"),
        "search_id": search_id,
    }

    try:
        formatted = _fan_out(request, supplier)
        meta = formatted["metadata"]
        meta["search_id"] = search_id
        meta["api_response_time_ms"] = int((time.monotonic() - t_start) * 1000)
        meta.update(client_meta)

        background_tasks.add_task(
            log_search_request,
            supplier=",".join(meta["suppliers_succeeded"]) or supplier,
            result_count=meta["total_results"],
            metadata={k: meta[k] for k in ("supplier_response_time_ms", "api_response_time_ms", *client_meta)},
            status="success",
            **log_kwargs,
        )
        return formatted
    except Exception as exc:
        background_tasks.add_task(
            log_search_request,
            supplier=supplier,
            metadata={"api_response_time_ms": int((time.monotonic() - t_start) * 1000), **client_meta},
            status="error",
            **log_kwargs,
        )
        return error_response(exc)
