"""
app/helpers/flight/price_guard.py

Re-check-price-before-submit for every money-moving post-booking action
(ticket issue, exchange/reissue, refund).

Every such action follows the same contract:
  1. The service obtains a LIVE quote from the supplier (reprice / exchange quote / refund quote).
  2. `assert_charge_confirmed` / `assert_refund_confirmed` compares that live amount with the
     amount the customer confirmed.
  3. Only if the check passes is the action submitted to the supplier.
  4. If it fails, PriceChangedError (HTTP 409) returns the fresh quote so the client can show it
     to the customer and resend with the new confirmed amount.

Quotes that cannot be re-run (e.g. a Sabre exchange, which stores a PQR in the PNR) are kept
in Redis under a `quote_id` so the confirm step submits exactly what the customer saw.
"""

import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from app.utils.flight.errors import PriceChangedError
from app.utils.redis_utils import redis_helper

DEFAULT_TOLERANCE = Decimal("1.00")   # currency units; override per supplier with settings.price_tolerance
QUOTE_TTL_MINUTES = 20
_QUOTE_KEY        = "flight_quote:{quote_id}"


def _dec(val: Any) -> Optional[Decimal]:
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def supplier_tolerance(svc: Any) -> Decimal:
    settings = getattr(getattr(svc, "config", None), "settings", None) or {}
    return _dec(settings.get("price_tolerance")) or DEFAULT_TOLERANCE


def _quote_payload(amount: Decimal, currency: str, extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = {"amount": float(amount), "currency": currency}
    if extra:
        payload.update(extra)
    return payload


def _check_currency(currency: str, confirmed_currency: Optional[str], quote: Dict[str, Any]) -> None:
    if confirmed_currency and currency and confirmed_currency.upper() != currency.upper():
        raise PriceChangedError(
            f"Supplier quoted in {currency} but the confirmed amount is in {confirmed_currency}. "
            f"Confirm the amount in {currency}.",
            quote,
        )


def assert_charge_confirmed(
    live_amount: Any,
    currency: str,
    confirmed_amount: Any,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    confirmed_currency: Optional[str] = None,
    quote_extra: Optional[Dict[str, Any]] = None,
) -> Decimal:
    """
    For actions where the customer PAYS the live amount (issue, exchange add-collect).
    Passes when live <= confirmed + tolerance. A lower live price is accepted.
    """
    live = _dec(live_amount)
    if live is None:
        raise PriceChangedError("Supplier did not return a price; cannot verify the fare before submitting.")
    quote = _quote_payload(live, currency, quote_extra)
    _check_currency(currency, confirmed_currency, quote)

    confirmed = _dec(confirmed_amount)
    if confirmed is None:
        raise PriceChangedError(
            f"Price confirmation required: the live amount is {currency} {live}. "
            f"Resend with this amount as the confirmed amount to proceed.",
            quote,
        )
    if live > confirmed + tolerance:
        raise PriceChangedError(
            f"Price increased from {currency} {confirmed} to {currency} {live}. "
            f"Customer must accept the new amount before submission.",
            quote,
        )
    return live


def assert_refund_confirmed(
    live_amount: Any,
    currency: str,
    confirmed_amount: Any,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    confirmed_currency: Optional[str] = None,
    quote_extra: Optional[Dict[str, Any]] = None,
) -> Decimal:
    """
    For refunds, where the customer RECEIVES the live amount.
    Passes when live >= confirmed - tolerance. A higher refund is accepted.
    """
    live = _dec(live_amount)
    if live is None:
        raise PriceChangedError("Supplier did not return a refund amount; cannot verify it before submitting.")
    quote = _quote_payload(live, currency, quote_extra)
    _check_currency(currency, confirmed_currency, quote)

    confirmed = _dec(confirmed_amount)
    if confirmed is None:
        raise PriceChangedError(
            f"Refund confirmation required: the live refundable amount is {currency} {live}. "
            f"Resend with this amount as the confirmed refund amount to proceed.",
            quote,
        )
    if live < confirmed - tolerance:
        raise PriceChangedError(
            f"Refundable amount dropped from {currency} {confirmed} to {currency} {live}. "
            f"Customer must accept the new amount before submission.",
            quote,
        )
    return live


# ── Quote store ───────────────────────────────────────────────────────────────

def save_quote(kind: str, data: Dict[str, Any]) -> str:
    quote_id = str(uuid.uuid4())
    redis_helper.set_data_ttl(
        _QUOTE_KEY.format(quote_id=quote_id),
        {"kind": kind, **data},
        ttl_minutes=QUOTE_TTL_MINUTES,
    )
    return quote_id


def load_quote(quote_id: str, kind: str, pnr: str) -> Dict[str, Any]:
    data = redis_helper.get_data(_QUOTE_KEY.format(quote_id=quote_id)) if quote_id else None
    if not data or data.get("kind") != kind:
        raise ValueError("Quote not found or expired. Request a new quote.")
    if str(data.get("pnr", "")).upper() != str(pnr or "").upper():
        raise ValueError("Quote does not belong to this PNR.")
    return data


def consume_quote(quote_id: str) -> None:
    try:
        redis_helper.delete_key(_QUOTE_KEY.format(quote_id=quote_id))
    except Exception:
        pass


def update_quote(quote_id: str, data: Dict[str, Any], ttl_minutes: int = QUOTE_TTL_MINUTES) -> None:
    """Merges `data` into a stored quote (e.g. records a stored PQR so a retry only reissues)."""
    key = _QUOTE_KEY.format(quote_id=quote_id)
    current = redis_helper.get_data(key) or {}
    redis_helper.set_data_ttl(key, {**current, **data}, ttl_minutes=ttl_minutes)
