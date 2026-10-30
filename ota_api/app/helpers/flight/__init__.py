"""
app/helpers/flight/__init__.py

Public API for the flight helper package.
FlightController imports everything from here — internal module layout is hidden.
"""

from app.helpers.flight.registry import (
    INTEGRATION_REGISTRY,
    DEFAULT_SUPPLIER,
    ALL_SUPPLIERS,
    is_provider_key,
    resolve_supplier,
    resolve_request_service,
    get_active_flight_suppliers,
)
from app.helpers.flight.logger import (
    log_search_request, log_booking, log_ticket,
    log_supplier_call, update_booking_status,
    get_booking_snapshot, to_bdt, log_ticket_status_change, log_refund,
)
from app.utils.flight import (
    format_error_response,
    format_search_response,
    format_pricing_response,
    format_pnr_response,
    format_pnr_details_response,
    format_cancel_response,
    format_ticketing_response,
    format_fare_rules_response,
    format_seat_map_response,
    format_baggage_response,
    format_refund_response,
    format_exchange_response,
    build_search_filters,
)

# Workflow modules (imported last: they depend on the modules above)
from app.helpers.flight.responses import error_response, handle_errors
from app.helpers.flight.search import run_flight_search
from app.helpers.flight import operations

__all__ = [
    "INTEGRATION_REGISTRY",
    "DEFAULT_SUPPLIER",
    "ALL_SUPPLIERS",
    "is_provider_key",
    "resolve_supplier",
    "resolve_request_service",
    "get_active_flight_suppliers",
    "log_search_request",
    "log_booking",
    "log_ticket",
    "log_supplier_call",
    "update_booking_status",
    "get_booking_snapshot",
    "to_bdt",
    "log_ticket_status_change",
    "log_refund",
    "format_error_response",
    "format_search_response",
    "format_pricing_response",
    "format_pnr_response",
    "format_pnr_details_response",
    "format_cancel_response",
    "format_ticketing_response",
    "format_fare_rules_response",
    "format_seat_map_response",
    "format_baggage_response",
    "format_refund_response",
    "format_exchange_response",
    "build_search_filters",
    "error_response",
    "handle_errors",
    "run_flight_search",
    "operations",
]
