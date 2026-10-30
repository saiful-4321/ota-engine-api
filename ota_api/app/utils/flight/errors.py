"""
app/utils/flight/errors.py

Typed exceptions for the flight stack. The controller maps each type to an HTTP status:

  ValueError                  → 400  (bad input from the caller)
  PriceChangedError           → 409  (fare moved since the customer confirmed it)
  OperationNotSupportedError  → 501  (provider integration does not support the operation)
  SupplierError               → 502  (provider rejected / failed the call)
  anything else               → 500  (bug in our code)
"""

from typing import Any, Dict, Optional


class SupplierError(Exception):
    """The supplier (Sabre / Travelport / ...) rejected or failed the request."""


class OperationNotSupportedError(Exception):
    """The operation is not available for this supplier integration."""


class PartialExchangeError(SupplierError):
    """
    The itinerary was changed and the reissue price record (PQR) stored, but the new ticket was
    not issued. `pqr_number` lets the confirm step retry only the reissue — never the exchange.
    """

    def __init__(self, message: str, pqr_number: Any = None):
        super().__init__(message)
        self.pqr_number = pqr_number


class PriceChangedError(Exception):
    """
    Raised by the price guard when the live supplier price differs from the amount
    the customer confirmed. `quote` carries the fresh price so the client can ask the
    customer to accept it and resend with the new confirmed amount.
    """

    def __init__(self, message: str, quote: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.quote = quote or {}
