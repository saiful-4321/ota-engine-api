"""
app/utils/flight/seat_maps.py

Turns supplier seat-map responses into one shape for the frontend:

    {
      "flight": {"carrier": "EK", "flight_number": "585", "origin": "DAC", "destination": "DXB", "departure_date": "2026-12-10"},
      "cabins": [{
        "cabin": "ECONOMY",
        "columns": [{"column": "A", "position": "window"}, ...],
        "rows": [{"row": 17, "seats": [{
            "seat": "17A", "column": "A",
            "status": "available" | "occupied" | "blocked" | "unavailable",
            "chargeable": true, "price": {"amount": 1683.0, "currency": "BDT"} | null,
            "features": ["window", "extra_legroom", ...], "codes": ["W", "L", ...]
        }]}]
      }]
    }

Both GDS use the IATA (PADIS) seat characteristic codes, so one table labels them.
`codes` keeps every raw code, including the ones without a label.
"""

from typing import Any, Dict, List, Optional

SEAT_FEATURES = {
    "W": "window",
    "A": "aisle",
    "9": "center",
    "E": "exit_row",
    "L": "extra_legroom",
    "K": "bulkhead",
    "B": "bassinet",
    "O": "preferred",
    "CH": "chargeable",
    "FC": "front_of_cabin",
    "T": "rear_of_cabin",
    "I": "suitable_for_infant",
    "1A": "no_infants",
    "IE": "not_suitable_for_child",
    "U": "suitable_for_unaccompanied_minor",
    "H": "accessible",
    "1": "restricted",
}

COLUMN_POSITIONS = {"W": "window", "A": "aisle", "C": "center"}

# Travelport seat availability → our status
_TRAVELPORT_STATUS = {"available": "available", "reserved": "occupied", "blocked": "blocked", "noseat": "unavailable"}


def _features(codes: List[str]) -> List[str]:
    return [SEAT_FEATURES[c] for c in codes if c in SEAT_FEATURES]


def _seat(row: Any, column: str, status: str, codes: List[str], price: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "seat": f"{row}{column}",
        "column": column,
        "status": status,
        "chargeable": "CH" in codes or bool(price and price["amount"]),
        "price": price,
        "features": _features(codes),
        "codes": codes,
    }


def _to_int(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


# ── Sabre (Get Seats, /v1/offers/getseats) ───────────────────────────────────

def _sabre_prices(response: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """offerItemID → {"amount", "currency"} from the à-la-carte seat offer."""
    prices = {}
    for item in (response.get("aLaCarteOffer") or {}).get("aLaCarteOfferItems", []):
        total = (item.get("unitPrice") or {}).get("totalAmount") or {}
        if item.get("offerItemID") and total.get("amount") is not None:
            prices[item["offerItemID"]] = {"amount": float(total["amount"]), "currency": total.get("currencyCode")}
    return prices


def _sabre_status(code: Optional[str]) -> str:
    return {"F": "available", "O": "occupied"}.get(code, "unavailable")


def _sabre_flight(response: Dict[str, Any]) -> Dict[str, Any]:
    segment = ((response.get("dataLists") or {}).get("paxSegments") or [{}])[0]
    departure, arrival = segment.get("departure") or {}, segment.get("arrival") or {}
    carrier = segment.get("marketingCarrierInfo") or {}
    return {
        "carrier": carrier.get("carrierDesignatorCode"),
        "flight_number": carrier.get("marketingCarrierFlightNumberText"),
        "origin": departure.get("iataLocationCode"),
        "destination": arrival.get("iataLocationCode"),
        "departure_date": (departure.get("aircraftScheduledDateTime") or "")[:10] or None,
    }


def _sabre_row(row: Dict[str, Any], prices: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    seats = []
    for seat in row.get("seats", []):
        codes = [c.get("code") for c in seat.get("characteristics", []) if c.get("code")]
        price = next((prices[ref] for ref in seat.get("offerItemRefIDs", []) if ref in prices), None)
        status = _sabre_status(seat.get("occupationStatusCode"))
        seats.append(_seat(row.get("row"), seat.get("column"), status, codes, price))
    return {"row": row.get("row"), "seats": seats}


def _sabre_cabin(compartment: Dict[str, Any], prices: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    layout = compartment.get("cabinLayout") or {}
    return {
        "cabin": (compartment.get("cabinType") or {}).get("cabinTypeName"),
        "columns": [{"column": c.get("id"), "position": COLUMN_POSITIONS.get(c.get("position"))}
                    for c in layout.get("columns", [])],
        "rows": [_sabre_row(row, prices) for row in compartment.get("seatRows", [])],
    }


def from_sabre(raw: Dict[str, Any]) -> Dict[str, Any]:
    response = raw.get("response") or {}
    prices = _sabre_prices(response)
    cabins = [_sabre_cabin(compartment, prices)
              for seat_map in response.get("seatMaps", [])
              for compartment in seat_map.get("cabinCompartments", [])]
    return {"flight": _sabre_flight(response), "cabins": cabins}


# ── Travelport (seat availability, standalone) ───────────────────────────────

def _offering_price(offering: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    detail = offering.get("Price") or {}
    if detail.get("TotalPrice") is None:
        return None
    return {"amount": float(detail["TotalPrice"]), "currency": (detail.get("CurrencyCode") or {}).get("value")}


def _availability_groups(offering: Dict[str, Any]):
    for option in offering.get("ProductOptions", []):
        for product in option.get("Product", []):
            yield from product.get("SeatAvailability", [])


def _travelport_seat_offers(offerings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Seat number → {"status", "price"}. Each CatalogOffering is one price point listing seats by
    status; a seat listed as Available in any offering is available at that offering's price.
    """
    seats: Dict[str, Dict[str, Any]] = {}
    for offering in offerings:
        price = _offering_price(offering)
        for group in _availability_groups(offering):
            status = _TRAVELPORT_STATUS.get(str(group.get("seatAvailabilityStatus", "")).lower(), "unavailable")
            for number in group.get("value", []):
                if number not in seats or (status == "available" and seats[number]["status"] != "available"):
                    seats[number] = {"status": status, "price": price if status == "available" else None}
    return seats


def _travelport_flight(response: Dict[str, Any]) -> Dict[str, Any]:
    flight = ((response.get("CatalogOfferingsID") or [{}])[0].get("Flight") or [{}])[0]
    departure = flight.get("Departure") or {}
    return {
        "carrier": flight.get("carrier"),
        "flight_number": flight.get("number"),
        "origin": departure.get("location"),
        "destination": (flight.get("Arrival") or {}).get("location"),
        "departure_date": departure.get("date"),
    }


def _travelport_row(row: Dict[str, Any], seat_offers: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    label = _to_int(row.get("label"))
    seats = []
    for space in row.get("Space", []):
        offer = seat_offers.get(f"{row.get('label')}{space.get('location')}", {"status": "unavailable", "price": None})
        price = offer["price"] if offer["price"] and offer["price"]["amount"] else None  # 0 = free seat
        seats.append(_seat(label, space.get("location"), offer["status"], space.get("Characteristic", []), price))
    return {"row": label, "seats": seats}


def _travelport_cabin(cabin: Dict[str, Any], seat_offers: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    # Layout: the first item holds the row range, the rest map a column letter to its position.
    columns = [{"column": item.get("value"), "position": COLUMN_POSITIONS.get((item.get("position") or [None])[0])}
               for item in cabin.get("Layout", []) if item.get("value")]
    return {"cabin": cabin.get("name"), "columns": columns,
            "rows": [_travelport_row(row, seat_offers) for row in cabin.get("Row", [])]}


def from_travelport(raw: Dict[str, Any]) -> Dict[str, Any]:
    response = raw.get("CatalogOfferingsAncillaryListResponse") or {}
    offerings = [o for group in response.get("CatalogOfferingsID", []) for o in group.get("CatalogOffering", [])]
    seat_offers = _travelport_seat_offers(offerings)
    cabins = [_travelport_cabin(cabin, seat_offers)
              for ref in response.get("ReferenceList", [])
              for chart in ref.get("SeatingChart", [])
              for cabin in chart.get("Cabin", [])]
    return {"flight": _travelport_flight(response), "cabins": cabins}
