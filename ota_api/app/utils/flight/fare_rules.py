"""
app/utils/flight/fare_rules.py

Change / refund rules in one shape for both suppliers:

    {
      "fare_rules": [{
        "route": "DAC-DXB", "airline": "EK", "flight_number": "587" | null,
        "passenger_types": ["ADT"], "fare_basis": "LLOWBD" | null,
        "refundable": true | false | null,
        "changeable": true | false | null,
        "penalties": [{
          "action": "refund" | "change",
          "allowed": true | false | null,        # null = the airline filed it as "conditions apply"
          "applies": ["before_departure", "no_show", ...],
          "amount": 75.0 | null, "currency": "USD" | null
        }]
      }],
      "rule_text": [{"title": "Penalties", "text": "CHG-50USD/CXL BEF DEP-75USD/..."}]
    }

`refundable` / `changeable` are the supplier's own flags (Sabre). Travelport files penalties as
several conditional records, so there they are true when at least one record permits the action,
false when every record forbids it, and null when the airline left it undetermined.
"""

import re
from typing import Any, Dict, List, Optional


def _snake(value: str) -> str:
    """'BeforeDeparture' / 'BEFORE_DEPARTURE' → 'before_departure'."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower() if not value.isupper() else value.lower()


def _penalty(action: str, allowed: Optional[bool], applies: List[str],
             amount: Optional[float] = None, currency: Optional[str] = None) -> Dict[str, Any]:
    return {"action": action, "allowed": allowed, "applies": applies, "amount": amount, "currency": currency}


def _overall(penalties: List[Dict[str, Any]], action: str) -> Optional[bool]:
    flags = [p["allowed"] for p in penalties if p["action"] == action and p["allowed"] is not None]
    if not flags:
        return None
    return any(flags)


# ── Sabre (getBooking → fareRules) ───────────────────────────────────────────

def _sabre_penalties(rule: Dict[str, Any], key: str, action: str, allowed: Optional[bool]) -> List[Dict[str, Any]]:
    penalties = []
    for item in rule.get(key) or []:
        amount = (item.get("penalty") or {})
        penalties.append(_penalty(
            action,
            None if item.get("conditionsApply") else allowed,
            [_snake(item["applicability"])] if item.get("applicability") else [],
            float(amount["amount"]) if amount.get("amount") is not None else None,
            amount.get("currencyCode"),
        ))
    if not penalties and allowed is False:
        penalties.append(_penalty(action, False, []))
    return penalties


def from_sabre_booking(booking: Dict[str, Any]) -> Dict[str, Any]:
    rules = []
    for rule in booking.get("fareRules") or []:
        refundable, changeable = rule.get("isRefundable"), rule.get("isChangeable")
        rules.append({
            "route": f"{rule.get('originAirportCode')}-{rule.get('destinationAirportCode')}",
            "airline": rule.get("owningAirlineCode"),
            "flight_number": None,
            "passenger_types": [rule["passengerCode"]] if rule.get("passengerCode") else [],
            "fare_basis": None,
            "refundable": refundable,
            "changeable": changeable,
            "penalties": (_sabre_penalties(rule, "refundPenalties", "refund", refundable)
                          + _sabre_penalties(rule, "exchangePenalties", "change", changeable)),
        })
    return {"fare_rules": rules, "rule_text": []}


# ── Travelport (FareRuleListResponse) ────────────────────────────────────────

def _travelport_flights(response: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    flights = {}
    for ref in response.get("ReferenceList", []):
        for flight in ref.get("Flight", []):
            flights[flight.get("id")] = flight
    return flights


def _travelport_entry(action: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    kind = entry.get("@type", "")  # ChangePermitted / CancelNotPermitted / ChangeIndeterminate ...
    if "NotPermitted" in kind:
        allowed = False
    elif "Permitted" in kind:
        allowed = True
    else:
        allowed = None
    amount = currency = None
    for penalty in entry.get("Penalty", []):
        if penalty.get("Amount"):
            amount, currency = float(penalty["Amount"].get("value")), penalty["Amount"].get("code")
            break
    return _penalty(action, allowed, [_snake(t) for t in entry.get("penaltyTypes", [])], amount, currency)


def _penalty_entries(structured_rules: List[Dict[str, Any]]):
    """(action, entry) for every Change / Cancel record in the structured rules."""
    for rule in structured_rules:
        for block in rule.get("Penalties", []):
            for entry in block.get("Change", []):
                yield "change", entry
            for entry in block.get("Cancel", []):
                yield "refund", entry


def _travelport_penalties(structured_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    penalties: List[Dict[str, Any]] = []
    for action, entry in _penalty_entries(structured_rules):
        item = _travelport_entry(action, entry)
        if item not in penalties:  # Travelport repeats records per fare component
            penalties.append(item)
    return penalties


def _passenger_types(rules: List[Dict[str, Any]]) -> List[str]:
    for rule in rules:
        codes = [c for c in rule.get("passengerTypeCodes") or [] if c and c != "null"]
        if codes:
            return codes
    return []


def from_travelport(response: Dict[str, Any], text_response: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = response.get("FareRuleListResponse") or {}
    flights = _travelport_flights(body)
    rules = []
    for fare_rule in body.get("FareRule", []):
        structured = fare_rule.get("StructuredFareRules", [])
        ref = (fare_rule.get("Flight") or [{}])[0].get("FlightRef")
        flight = flights.get(ref, {})
        penalties = _travelport_penalties(structured)
        rules.append({
            "route": f"{(flight.get('Departure') or {}).get('location')}-{(flight.get('Arrival') or {}).get('location')}"
                     if flight else None,
            "airline": flight.get("carrier"),
            "flight_number": flight.get("number"),
            "passenger_types": _passenger_types(structured),
            "fare_basis": None,  # Travelport returns the rule's match pattern (e.g. '&&&&P&&&'), not the fare basis
            "refundable": _overall(penalties, "refund"),
            "changeable": _overall(penalties, "change"),
            "penalties": penalties,
        })
    return {"fare_rules": rules, "rule_text": travelport_rule_text(text_response) if text_response else []}


def travelport_rule_text(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Category text (Penalties, Advance Res/Tkt, ...) — empty categories are skipped."""
    text = []
    for fare_rule in (response.get("FareRuleListResponse") or {}).get("FareRule", []):
        for category in fare_rule.get("TextFareRule", []):
            if (category.get("value") or "").strip():
                text.append({"title": category.get("name"), "text": category["value"].strip()})
    return text
