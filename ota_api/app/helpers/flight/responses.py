"""
app/helpers/flight/responses.py

HTTP error mapping for the flight endpoints:

  ValueError                  → 400
  PriceChangedError           → 409  (body carries error_code=PRICE_CHANGED and the fresh `quote`)
  OperationNotSupportedError  → 501
  SupplierError               → 502
  anything else               → 500  (logged; internals are not leaked)
"""

import functools

from fastapi.responses import JSONResponse

from app.helpers.common import write_log
from app.utils.flight.errors import SupplierError, OperationNotSupportedError, PriceChangedError
from app.utils.flight import format_error_response


def error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, PriceChangedError):
        body = format_error_response(exc)
        body.update({"error_code": "PRICE_CHANGED", "quote": exc.quote})
        return JSONResponse(status_code=409, content=body)
    if isinstance(exc, ValueError):
        return JSONResponse(status_code=400, content=format_error_response(exc))
    if isinstance(exc, OperationNotSupportedError):
        return JSONResponse(status_code=501, content=format_error_response(exc))
    if isinstance(exc, SupplierError):
        return JSONResponse(status_code=502, content=format_error_response(exc))
    write_log(exc, source="FlightController", type="error")
    return JSONResponse(
        status_code=500,
        content=format_error_response(Exception("Internal error while processing the flight request")),
    )


def handle_errors(func):
    """Endpoint decorator: turns any exception into the mapped JSON error response."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            return error_response(exc)
    return wrapper
