from decimal import Decimal, ROUND_HALF_UP
from typing import Union

# The canonical stored currency for this system
DEFAULT_CURRENCY: str = "BDT"

# Precision used for stored amounts (2 decimal places)
_AMOUNT_QUANT = Decimal("0.01")

# Precision used for stored conversion rates (6 decimal places)
_RATE_QUANT = Decimal("0.000001")


def convert_to_bdt(
    amount: Union[float, Decimal, str, None],
    source_currency: str,
    rate: Union[float, Decimal, str, None] = None,
) -> Decimal:
    if amount is None:
        return Decimal("0.00")

    dec_amount = Decimal(str(amount))

    # Already in BDT — no conversion needed
    if (source_currency or "").upper() == DEFAULT_CURRENCY:
        return dec_amount.quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP)

    # No rate provided for a foreign currency — return as-is with a warning
    if rate is None:
        import logging
        logging.getLogger(__name__).warning(
            "convert_to_bdt: no conversion rate supplied for %s → BDT. "
            "Storing amount as-is (%s). Supply `conversion_rate_to_bdt` in "
            "price_info to enable proper BDT conversion.",
            source_currency, dec_amount,
        )
        return dec_amount.quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP)

    dec_rate = Decimal(str(rate))
    bdt = dec_amount * dec_rate
    return bdt.quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP)


def normalize_rate(
    rate: Union[float, Decimal, str, None],
    source_currency: str,
) -> Decimal:
    if (source_currency or "").upper() == DEFAULT_CURRENCY or rate is None:
        return Decimal("1.000000")

    return Decimal(str(rate)).quantize(_RATE_QUANT, rounding=ROUND_HALF_UP)
