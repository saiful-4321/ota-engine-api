"""
app/helpers/sabre_helper.py  —  DEPRECATED shim

All Sabre formatting logic has moved to:
    app/helpers/flight/formatters/sabre.py

This file re-exports everything so any code still referencing
`from app.helpers.sabre_helper import ...` continues to work
without modification.
"""

from app.utils.flight.sabre import (   # noqa: F401
    wrap_response,
    format_bfm_response,
    format_pnr_response,
    format_pnr_details_response,
    format_ticketing_response,
    format_pricing_response,
    format_cancel_response,
    format_fare_rules_response,
    format_error_response,
)
