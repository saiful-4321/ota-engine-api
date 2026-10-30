"""
app/utils/flight/baggage.py

Baggage allowance of a booked PNR in one shape for both suppliers:

    {
      "allowances": [{
        "passenger_types": ["ADT"],
        "segments": ["DAC-DXB"],
        "checked": {"pieces": null, "weight_kg": 30, "text": "30K"},
        "cabin":   {"pieces": 1, "weight_kg": 7, "text": null} | null
      }],
      "excess_baggage": [{"description": "...", "pieces": 1, "max_weight_kg": 10, "fee": {"amount": 70.0, "currency": "USD"}}]
    }

Sources: Sabre getBooking (`fareOffers`, falling back to `fares[].fareConstruction`) and the
Travelport reservation (`Offer[].TermsAndConditionsFull[].BaggageAllowance`).
"""

import re
from typing import Any, Dict, List, Optional

_TEXT_PATTERN = re.compile(r"^\s*(\d+)\s*(K|KG|KGS|P|PC|PCS)\s*$", re.IGNORECASE)


def _allowance(pieces: Optional[int] = None, weight_kg: Optional[float] = None, text: Optional[str] = None) -> Dict[str, Any]:
    return {"pieces": pieces, "weight_kg": weight_kg, "text": text}


def parse_allowance_text(text: str) -> Dict[str, Any]:
    """'30K' → 30 kg, '2P' / '2PC' → 2 pieces; anything else is kept as text only."""
    match = _TEXT_PATTERN.match(text or "")
    if not match:
        return _allowance(text=text)
    number, unit = int(match.group(1)), match.group(2).upper()
    return _allowance(weight_kg=number, text=text) if unit.startswith("K") else _allowance(pieces=number, text=text)


# ── Sabre (getBooking) ───────────────────────────────────────────────────────

def _sabre_allowance(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not node:
        return None
    return _allowance(pieces=node.get("maximumPieces"), weight_kg=node.get("totalWeightInKilograms"))


def _sabre_excess_charge(charge: Dict[str, Any]) -> Dict[str, Any]:
    fee = charge.get("fee") or {}
    return {
        "description": charge.get("specialItemDescription") or "Additional checked bag",
        "pieces": charge.get("numberOfPieces"),
        "max_weight_kg": charge.get("maximumWeightInKilograms"),
        "fee": {"amount": float(fee["amount"]), "currency": fee.get("currencyCode")} if fee.get("amount") else None,
    }


def _sabre_fare_construction_allowances(booking: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Older or partially priced bookings carry the checked allowance only on the fare construction."""
    allowances = []
    for fare in booking.get("fares") or []:
        passenger_types = [fare["pricedTravelerType"]] if fare.get("pricedTravelerType") else []
        for component in fare.get("fareConstruction") or []:
            if component.get("checkedBaggageAllowance"):
                allowances.append({"passenger_types": passenger_types, "segments": [],
                                   "checked": _sabre_allowance(component["checkedBaggageAllowance"]), "cabin": None})
    return allowances


def from_sabre(booking: Dict[str, Any]) -> Dict[str, Any]:
    travelers = booking.get("travelers") or []
    routes = {f.get("itemId"): f"{f.get('fromAirportCode')}-{f.get('toAirportCode')}" for f in booking.get("flights") or []}

    allowances, excess = [], []
    for offer in booking.get("fareOffers") or []:
        indices = [i for i in offer.get("travelerIndices", []) if 0 < i <= len(travelers)]  # 1-based
        allowances.append({
            "passenger_types": sorted({travelers[i - 1].get("passengerCode") for i in indices} - {None}),
            "segments": [routes[f.get("itemId")] for f in offer.get("flights", []) if f.get("itemId") in routes],
            "checked": _sabre_allowance(offer.get("checkedBaggageAllowance")),
            "cabin": _sabre_allowance(offer.get("cabinBaggageAllowance")),
        })
        for charge in map(_sabre_excess_charge, offer.get("checkedBaggageCharges") or []):
            if charge not in excess:
                excess.append(charge)

    return {"allowances": allowances or _sabre_fare_construction_allowances(booking), "excess_baggage": excess}


# ── Travelport (reservation retrieve) ────────────────────────────────────────

def _travelport_routes(offer: Dict[str, Any]) -> Dict[int, str]:
    routes = {}
    for product in offer.get("Product", []):
        for segment in product.get("FlightSegment", []):
            flight = segment.get("Flight") or {}
            routes[segment.get("sequence")] = (f"{(flight.get('Departure') or {}).get('location')}-"
                                               f"{(flight.get('Arrival') or {}).get('location')}")
    return routes


def from_travelport(reservation_response: Dict[str, Any]) -> Dict[str, Any]:
    reservation = (reservation_response.get("ReservationResponse") or {}).get("Reservation") or {}
    allowances: List[Dict[str, Any]] = []
    for offer in reservation.get("Offer", []):
        routes = _travelport_routes(offer)
        for terms in offer.get("TermsAndConditionsFull", []):
            for detail in terms.get("BaggageAllowance") or []:
                texts = detail.get("Text") or []
                allowances.append({
                    "passenger_types": detail.get("passengerTypeCodes") or [],
                    "segments": [routes.get(seq, str(seq)) for seq in detail.get("SegmentSequenceList", [])],
                    "checked": parse_allowance_text(texts[0]) if texts else None,
                    "cabin": None,
                })
    # Travelport does not return excess-baggage prices on the reservation.
    return {"allowances": allowances, "excess_baggage": []}
