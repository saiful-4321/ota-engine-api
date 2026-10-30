import json
import re
import requests
from app.services.sabre_auth_service import SabreBaseService
from app.models.flight_schemas import (
    FlightSearchRequest, FlightPricingRequest, FlightBookingRequest, TicketingRequest,
    PNRDetailsRequest, CancelItineraryRequest, VoidTicketRequest, ExchangeTicketRequest,
    ExchangeQuoteRequest, RefundQuoteRequest, RefundTicketRequest,
    SeatMapRequest, BaggageAllowanceRequest, QueueRequest, FareRulesRequest
)
from app.utils.flight.errors import (
    SupplierError, PriceChangedError, PartialExchangeError, OperationNotSupportedError,
)
from app.helpers.common import write_log
import datetime
from app.services.sabre_endpoints import SabreEndpoints
from typing import Optional, Dict, Any
from app.services.supplier_config_service import SupplierConfig


def _extract_datetime_parts(val: Any) -> tuple:
    """Extracts (YYYY-MM-DD, HH:MM) from any date/time string or object."""
    if not val:
        return ("", "")
    if isinstance(val, datetime.datetime):
        return (val.strftime("%Y-%m-%d"), val.strftime("%H:%M"))
    if isinstance(val, datetime.date):
        return (val.strftime("%Y-%m-%d"), "")
    if isinstance(val, dict):
        d = str(val.get("date") or "").strip()[:10]
        t = str(val.get("time") or "").strip()
        if not d and val.get("dateTime"):
            return _extract_datetime_parts(val["dateTime"])
        if t and len(t) >= 5 and ":" in t:
            t = t[:5]
        return (d, t)

    s = str(val).strip()
    # Check if format starts with YYYY-MM-DD
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        date_part = s[:10]
        time_part = ""
        rest = s[10:].strip().lstrip("T").strip()
        if len(rest) >= 5 and ":" in rest:
            time_part = rest[:5]
        return (date_part, time_part)

    # Check if format is purely time HH:MM...
    if ":" in s:
        t_clean = s.replace("Z", "").strip()
        if "+" in t_clean:
            t_clean = t_clean.split("+")[0].strip()
        elif "-" in t_clean and len(t_clean.split("-")) > 1 and ":" in t_clean.split("-")[-1]:
            t_clean = t_clean.rsplit("-", 1)[0].strip()
        if len(t_clean) >= 5 and ":" in t_clean:
            return ("", t_clean[:5])

    return ("", "")


def _is_valid_airline_code(code: Any) -> bool:
    """Validates that an airline code matches Sabre format: 2-char alphanumeric (with at least one letter) or 3-letter ICAO."""
    if not code or not isinstance(code, str):
        return False
    c = code.strip().upper()
    if c.isdigit():
        return False
    return bool(re.match(r"^([A-Z0-9]{2}|[A-Z]{3})$", c))


def _parse_sabre_segment(segment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Robustly extracts and normalizes flight segment fields across any schema format:
      - Frontend search response (camelCase with nested dicts)
      - Backoffice / DB model format (carrier_code, departure_at, departure_time with datetime strings)
      - Standard snake_case schema (airline_code, carrier_code, origin, destination, etc.)
      - Raw Sabre POS / RQ schema (PascalCase like DepartureDateTime, ResBookDesigCode, etc.)
      - Mixed flat dictionaries
    """
    # 1. Marketing Airline
    candidates = [
        segment.get("carrier_code"),
        segment.get("carrierCode"),
        segment.get("marketing_carrier"),
        segment.get("marketingCarrier"),
        segment.get("marketing_carrier_code"),
        segment.get("marketingCarrierCode"),
        segment.get("airline_code"),
        segment.get("airlineCode"),
        segment.get("marketingAirlineCode"),
        segment.get("marketing_airline"),
        segment.get("carrier"),
        segment.get("airline"),
        segment.get("MarketingAirline"),
        segment.get("validating_carrier"),
        segment.get("validatingCarrier"),
    ]
    marketing_code = ""
    for cand in candidates:
        if not cand:
            continue
        if isinstance(cand, dict):
            for sub_k in ["code", "Code", "marketing", "carrier_code", "airline_code", "iata", "IATA"]:
                val = cand.get(sub_k)
                if isinstance(val, str) and _is_valid_airline_code(val):
                    marketing_code = val.strip().upper()
                    break
        elif isinstance(cand, str) and _is_valid_airline_code(cand):
            marketing_code = cand.strip().upper()
        if marketing_code:
            break

    # 2. Flight Number & Airline Code from FlightNumber (e.g. 'QR641' or 'QR 641')
    fn_raw = (
        segment.get("flight_number")
        or segment.get("flightNumber")
        or segment.get("FlightNumber")
        or segment.get("marketing_flight_number")
        or segment.get("marketingFlightNumber")
        or segment.get("marketing_flight_no")
    )
    if not fn_raw and isinstance(segment.get("MarketingAirline"), dict):
        fn_raw = segment["MarketingAirline"].get("FlightNumber")
    if not fn_raw and isinstance(segment.get("airline"), dict):
        fn_raw = segment["airline"].get("marketingFlightNumber") or segment["airline"].get("flightNumber")

    if not marketing_code and fn_raw and isinstance(fn_raw, str):
        # Extract airline prefix if it contains letters (e.g. 'SQ101', 'BG-641', '6E123')
        m = re.match(r"^([A-Za-z]{2,3}|[A-Za-z][0-9]|[0-9][A-Za-z])\s*[-]?\s*(\d+)$", str(fn_raw).strip())
        if m and _is_valid_airline_code(m.group(1)):
            marketing_code = m.group(1).upper()

    fn_digits = "".join(c for c in str(fn_raw or "") if c.isdigit())
    flight_number_int = int(fn_digits) if fn_digits else 0
    flight_number_str = fn_digits if fn_digits else str(fn_raw or "").strip()

    # 3. Operating Airline
    op_candidates = [
        segment.get("operating_carrier"),
        segment.get("operatingCarrier"),
        segment.get("operating_airline"),
        segment.get("operating_airline_code"),
        segment.get("operatingAirlineCode"),
        segment.get("OperatingAirline"),
    ]
    operating_code = None
    for cand in op_candidates:
        if not cand:
            continue
        if isinstance(cand, dict):
            for sub_k in ["code", "Code", "operating", "carrier_code", "airline_code", "iata", "IATA"]:
                val = cand.get(sub_k)
                if isinstance(val, str) and _is_valid_airline_code(val):
                    operating_code = val.strip().upper()
                    break
        elif isinstance(cand, str) and _is_valid_airline_code(cand):
            operating_code = cand.strip().upper()
        if operating_code:
            break

    # Fallback marketing_code to operating_code or validating_carrier if still empty
    if not marketing_code:
        if operating_code and _is_valid_airline_code(operating_code):
            marketing_code = operating_code
        else:
            vc = segment.get("validating_carrier") or segment.get("validatingCarrier")
            if isinstance(vc, str) and _is_valid_airline_code(vc):
                marketing_code = vc.strip().upper()

    marketing_code = str(marketing_code or "").strip().upper()

    # 4. Origin Code
    orig_val = (
        segment.get("OriginLocation")
        or segment.get("origin_code")
        or segment.get("originCode")
        or segment.get("originAirportCode")
        or segment.get("origin_airport")
        or segment.get("originAirport")
        or segment.get("departure_airport")
        or segment.get("departureAirport")
        or segment.get("departureAirportCode")
        or segment.get("origin")
        or segment.get("departure")
    )
    origin_code = ""
    if isinstance(orig_val, dict):
        origin_code = (
            orig_val.get("LocationCode")
            or orig_val.get("code")
            or orig_val.get("airport")
            or orig_val.get("airport_code")
            or ""
        )
    elif isinstance(orig_val, str):
        val_clean = orig_val.strip()
        if len(val_clean) == 3:
            origin_code = val_clean
    if not origin_code:
        raw_orig = segment.get("origin")
        if isinstance(raw_orig, str) and len(raw_orig.strip()) == 3:
            origin_code = raw_orig.strip()
    origin_code = str(origin_code or "").strip().upper()

    # 5. Destination Code
    dest_val = (
        segment.get("DestinationLocation")
        or segment.get("destination_code")
        or segment.get("destinationCode")
        or segment.get("arrivalAirportCode")
        or segment.get("destination_airport")
        or segment.get("destinationAirport")
        or segment.get("arrival_airport")
        or segment.get("arrivalAirport")
        or segment.get("arrivalAirportCode")
        or segment.get("destination")
        or segment.get("arrival")
    )
    dest_code = ""
    if isinstance(dest_val, dict):
        dest_code = (
            dest_val.get("LocationCode")
            or dest_val.get("code")
            or dest_val.get("airport")
            or dest_val.get("airport_code")
            or ""
        )
    elif isinstance(dest_val, str):
        val_clean = dest_val.strip()
        if len(val_clean) == 3:
            dest_code = val_clean
    if not dest_code:
        raw_dest = segment.get("destination")
        if isinstance(raw_dest, str) and len(raw_dest.strip()) == 3:
            dest_code = raw_dest.strip()
    dest_code = str(dest_code or "").strip().upper()

    # 6. Departure Date & Time
    dep_date = ""
    dep_time = ""
    for k in [
        "departure_at", "departure_time", "departure_date", "departureDate",
        "dep_date", "dep_time", "departureDateTime", "DepartureDateTime", "departure"
    ]:
        if k in segment and segment[k]:
            d, t = _extract_datetime_parts(segment[k])
            if not dep_date and d:
                dep_date = d
            if not dep_time and t:
                dep_time = t
            if dep_date and dep_time:
                break

    if not dep_date:
        dep_date = datetime.date.today().isoformat()
    if not dep_time:
        dep_time = "00:00"

    dep_time_seconds = f"{dep_time}:00" if len(dep_time) == 5 else dep_time
    dep_datetime = f"{dep_date}T{dep_time_seconds}"

    # 7. Arrival Date & Time
    arr_date = ""
    arr_time = ""
    for k in [
        "arrival_at", "arrival_time", "arrival_date", "arrivalDate",
        "arr_date", "arr_time", "arrivalDateTime", "ArrivalDateTime", "arrival"
    ]:
        if k in segment and segment[k]:
            d, t = _extract_datetime_parts(segment[k])
            if not arr_date and d:
                arr_date = d
            if not arr_time and t:
                arr_time = t
            if arr_date and arr_time:
                break

    if not arr_date:
        arr_date = dep_date
    if not arr_time:
        arr_time = "23:59"

    arr_time_seconds = f"{arr_time}:00" if len(arr_time) == 5 else arr_time
    arr_datetime = f"{arr_date}T{arr_time_seconds}"

    # 8. Booking Class / Cabin Class
    b_class = (
        segment.get("booking_class")
        or segment.get("bookingClass")
        or segment.get("booking_code")
        or segment.get("bookingCode")
        or segment.get("cabin_class")
        or segment.get("cabinClass")
        or segment.get("ResBookDesigCode")
        or segment.get("resBookDesigCode")
        or segment.get("CabinCode")
        or segment.get("Cabin")
    )
    if not b_class and isinstance(segment.get("details"), dict):
        b_class = (
            segment["details"].get("bookingClass")
            or segment["details"].get("bookingCode")
            or segment["details"].get("cabinClass")
        )

    if isinstance(b_class, dict):
        booking_class = b_class.get("code") or b_class.get("Code") or "Y"
    elif isinstance(b_class, str) and b_class.strip():
        booking_class = b_class.strip().upper()
    else:
        booking_class = "Y"

    return {
        "origin": origin_code,
        "destination": dest_code,
        "departure_date": dep_date,
        "departure_time": dep_time,
        "departure_datetime": dep_datetime,
        "arrival_date": arr_date,
        "arrival_time": arr_time,
        "arrival_datetime": arr_datetime,
        "marketing_airline": marketing_code,
        "operating_airline": operating_code,
        "flight_number_int": flight_number_int,
        "flight_number_str": flight_number_str,
        "booking_class": booking_class
    }


def _to_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _as_list(val: Any) -> list:
    if val is None:
        return []
    return val if isinstance(val, list) else [val]


def _find_all(obj: Any, key: str) -> list:
    """Collects every value stored under `key` anywhere in a nested dict/list."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            found.extend(_find_all(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_all(item, key))
    return found


def extract_sabre_price_quote(res_data: dict) -> dict:
    """
    Extracts the stored price quote totals from a CreatePassengerNameRecordRS / UpdatePassengerNameRecordRS
    (AirPrice with Retain=true).

    Returns: total_fare, base_fare, tax_amount, currency, quote_numbers
    (total_fare is 0 when no priced itinerary is present).
    """
    pricing = {"total_fare": 0.0, "base_fare": 0.0, "tax_amount": 0.0, "currency": None, "quote_numbers": []}
    res_data = res_data or {}
    rs = res_data.get("CreatePassengerNameRecordRS") or res_data.get("UpdatePassengerNameRecordRS") or {}

    for air_price in _as_list(rs.get("AirPrice")):
        for pq in _as_list(air_price.get("PriceQuote")):
            rph = pq.get("RPH") or pq.get("Number")
            if rph and str(rph).isdigit():
                pricing["quote_numbers"].append(int(rph))

            for pit in _as_list(pq.get("PricedItinerary")) or _as_list(air_price.get("PricedItinerary")):
                total = _to_float(pit.get("TotalAmount"))
                base = tax = 0.0
                for info in _as_list(pit.get("AirItineraryPricingInfo")):
                    qty = int(_to_float((info.get("PassengerTypeQuantity") or {}).get("Quantity")) or 1)
                    itin = info.get("ItinTotalFare") or {}
                    # EquivFare is the base fare in the ticketing currency when filed in another currency
                    base_node = itin.get("EquivFare") or itin.get("BaseFare") or {}
                    base += _to_float(base_node.get("Amount")) * qty
                    tax += _to_float((itin.get("Taxes") or {}).get("TotalAmount")) * qty
                    if not total:
                        total += _to_float((itin.get("TotalFare") or {}).get("Amount")) * qty
                    pricing["currency"] = pricing["currency"] or (itin.get("TotalFare") or {}).get("CurrencyCode")
                pricing["total_fare"] += total
                pricing["base_fare"] += base
                pricing["tax_amount"] += tax
                pricing["currency"] = pit.get("CurrencyCode") or pricing["currency"]

    if pricing["total_fare"] and not pricing["tax_amount"] and pricing["base_fare"]:
        pricing["tax_amount"] = round(pricing["total_fare"] - pricing["base_fare"], 2)
    pricing["total_fare"] = round(pricing["total_fare"], 2)
    pricing["base_fare"] = round(pricing["base_fare"], 2)
    pricing["tax_amount"] = round(pricing["tax_amount"], 2)
    return pricing


def _sabre_messages(app_results: dict) -> list:
    """Error and warning texts from a Sabre ApplicationResults node."""
    out = []
    for section in ("Error", "Warning"):
        for item in _as_list(app_results.get(section)):
            for sys_res in _as_list((item or {}).get("SystemSpecificResults")):
                for msg in _as_list((sys_res or {}).get("Message")):
                    text = str((msg or {}).get("content") or (msg or {}).get("value") or "").replace("\u0087", "").replace("‡", "").strip()
                    if text and text not in out:
                        out.append(text)
    return out


def _is_active_fare(fare: dict) -> bool:
    status = str(fare.get("pricingStatusCode") or fare.get("pricingStatusName") or "A").upper()
    return status in ("A", "ACTIVE")


def extract_booking_fares(booking: dict) -> dict:
    """
    Reads the stored price quotes from a Booking Management getBooking response (`fares`, one entry
    per active PQ, referenced by `recordId`).

    When a PNR holds several PQs for the same travellers (e.g. after a reprice), only the newest one
    per traveller group is kept, so tickets are never issued twice for the same passenger.

    Returns: total_fare, base_fare, tax_amount, currency, quote_numbers (empty when no active PQ).
    """
    data = (booking or {}).get("trip", booking or {})
    latest: Dict[tuple, dict] = {}
    for fare in _as_list(data.get("fares")):
        if not isinstance(fare, dict) or not _is_active_fare(fare):
            continue
        group = tuple(fare.get("travelerIndices") or [fare.get("requestedTravelerType") or fare.get("pricedTravelerType")])
        rid = int(_to_float(fare.get("recordId")) or 0)
        if group not in latest or rid > int(_to_float(latest[group].get("recordId")) or 0):
            latest[group] = fare

    pricing = {"total_fare": 0.0, "base_fare": 0.0, "tax_amount": 0.0, "currency": None, "quote_numbers": []}
    for fare in latest.values():
        totals = fare.get("totals") or {}
        travellers = len(fare.get("travelerIndices") or []) or 1
        pricing["total_fare"] += _to_float(totals.get("total")) * travellers
        pricing["base_fare"] += _to_float(totals.get("subtotal")) * travellers
        pricing["tax_amount"] += _to_float(totals.get("taxes")) * travellers
        pricing["currency"] = pricing["currency"] or totals.get("currencyCode")
        if fare.get("recordId") is not None:
            pricing["quote_numbers"].append(int(_to_float(fare["recordId"])))

    # With exactly one PQ per traveller group, Sabre's own grand total is authoritative
    flight_totals = _as_list((data.get("payments") or {}).get("flightTotals"))
    if flight_totals and len(latest) == len([f for f in _as_list(data.get("fares")) if isinstance(f, dict) and _is_active_fare(f)]):
        ft = flight_totals[0] if isinstance(flight_totals[0], dict) else {}
        if _to_float(ft.get("total")):
            pricing["total_fare"] = _to_float(ft.get("total"))
            pricing["base_fare"] = _to_float(ft.get("subtotal")) or pricing["base_fare"]
            pricing["tax_amount"] = _to_float(ft.get("taxes")) or pricing["tax_amount"]
            pricing["currency"] = ft.get("currencyCode") or pricing["currency"]

    pricing["quote_numbers"].sort()
    for key in ("total_fare", "base_fare", "tax_amount"):
        pricing[key] = round(pricing[key], 2)
    return pricing


def _validating_carrier_qualifier(carrier: Optional[str]) -> dict:
    """
    AirPrice OptionalQualifiers entry forcing the validating (plating) carrier — the WPC override.
    CreatePassengerNameRecordRQ v2.4.0 has no `ValidatingCarrier` property; the carrier goes in
    FlightQualifiers.VendorPrefs.Airline. Binds the stored PQ to a carrier this PCC can ticket on.
    """
    code = str(carrier or "").strip().upper()
    if not code:
        return {}
    return {"FlightQualifiers": {"VendorPrefs": {"Airline": {"Code": code}}}}


def _sabre_ptc(ptc: Optional[str]) -> str:
    ptc = str(ptc or "ADT").upper()
    return "CNN" if ptc == "CHD" else ptc


class SabreFlightService(SabreBaseService):

    def __init__(self, config: Optional[SupplierConfig] = None):
        super().__init__(config=config)

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _post(self, endpoint: str, payload: dict, action: str, timeout: int = 45,
              unknown_outcome_on_timeout: bool = False) -> dict:
        """
        POSTs to Sabre with a timeout and one token refresh on 401.
        `unknown_outcome_on_timeout` marks calls (PNR create, ticketing, refund) where a read
        timeout means the supplier may have completed the action — the caller must check
        the PNR before retrying instead of resubmitting blindly.
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.post(url, headers=self.get_headers(), json=payload, timeout=timeout)
            if response.status_code == 401:
                with self._lock:
                    self._refresh_token()
                response = self.session.post(url, headers=self.get_headers(), json=payload, timeout=timeout)
        except requests.exceptions.ReadTimeout as e:
            if unknown_outcome_on_timeout:
                raise SupplierError(
                    f"{action}: Sabre did not respond in {timeout}s — the outcome is UNKNOWN. "
                    f"Retrieve the PNR to check before retrying. ({e})"
                )
            raise SupplierError(f"{action} failed: Sabre timed out after {timeout}s")
        except requests.exceptions.RequestException as e:
            raise SupplierError(f"{action} failed. {e}")

        if response.status_code >= 400:
            write_log(f"Sabre {action} error: POST {url} | {response.status_code} | {response.text}",
                      source="sabre_service", type="error")
            raise SupplierError(f"{action} failed. HTTP {response.status_code} | Details: {response.text}")
        try:
            return response.json()
        except ValueError:
            raise SupplierError(f"{action} failed: Sabre returned a non-JSON response")

    def _invalidate_token(self) -> None:
        try:
            from app.utils.redis_utils import redis_helper
            redis_helper.delete_key(self.token_cache_key)
        except Exception as exc:
            print(f"[WARN] Failed to invalidate cached Sabre token: {exc}", flush=True)
        self._access_token = None
        self._token_expiry = 0.0

    # ── Shopping ─────────────────────────────────────────────────────────────

    def search_flights(self, search_params: FlightSearchRequest) -> dict:
        """
        Calls Sabre's Bargain Finder Max (BFM) API to search for flights.
        """
        origin_dest_info = []
        trip_type = (search_params.trip_type or "one_way").lower()

        if trip_type == "multi_city" and search_params.segments:
            for idx, seg in enumerate(search_params.segments):
                origin_dest_info.append({
                    "RPH": str(idx + 1),
                    "DepartureDateTime": seg.departure_date + "T00:00:00",
                    "OriginLocation": {"LocationCode": seg.origin.upper()},
                    "DestinationLocation": {"LocationCode": seg.destination.upper()}
                })
        else:
            origin_dest_info.append({
                "RPH": "1",
                "DepartureDateTime": search_params.departure_date + "T00:00:00",
                "OriginLocation": {"LocationCode": search_params.origin.upper()},
                "DestinationLocation": {"LocationCode": search_params.destination.upper()}
            })

        # Lap infants do not occupy a seat
        seats_requested = search_params.adults + search_params.children

        payload = {
            "OTA_AirLowFareSearchRQ": {
                "Version": "4.3.0",
                "POS": {
                    "Source": [
                        {
                            "PseudoCityCode": self.pcc,
                            "RequestorID": {
                                "Type": "1",
                                "ID": "1",
                                "CompanyName": {"Code": "TN"}
                            }
                        }
                    ]
                },
                "OriginDestinationInformation": origin_dest_info,
                "TravelerInfoSummary": {
                    "SeatsRequested": [seats_requested],
                    "AirTravelerAvail": [
                        {
                            "PassengerTypeQuantity": [
                                {"Code": "ADT", "Quantity": search_params.adults}
                            ]
                        }
                    ]
                },
                "TPA_Extensions": {
                    "IntelliSellTransaction": {
                        "RequestType": {"Name": "50ITINS"}
                    }
                }
            }
        }
        rq = payload["OTA_AirLowFareSearchRQ"]
        tpa_extensions = rq["TPA_Extensions"]

        # 1. Flexible Dates (+/- 1 to 3 days)
        if search_params.flexible_dates:
            tpa_extensions["IntelliSellTransaction"]["RequestType"]["Name"] = "ADRC"

        # 2. Direct Flights & Max Stops
        if search_params.direct_flights_only or search_params.max_stops is not None:
            stop_qty = 0 if search_params.direct_flights_only else search_params.max_stops
            rq.setdefault("TravelPreferences", {})["MaxStopsQuantity"] = stop_qty

        # 3. Included & Excluded Airlines
        if search_params.included_airlines or search_params.excluded_airlines:
            vendor_prefs = []
            for airline in search_params.included_airlines or []:
                vendor_prefs.append({"Code": airline, "Type": "Marketing"})
            for airline in search_params.excluded_airlines or []:
                vendor_prefs.append({"Code": airline, "Type": "Marketing", "Exclude": True})
            rq.setdefault("TravelPreferences", {})["VendorPref"] = vendor_prefs

        # 3.5 Cabin Class Preference
        if search_params.cabin_class:
            cabin_req = search_params.cabin_class.upper()
            prefs = rq.setdefault("TravelPreferences", {})
            if cabin_req == "ALL":
                prefs["CabinPref"] = [
                    {"Cabin": c, "PreferLevel": "Preferred"} for c in ("Y", "S", "C", "J", "F", "P")
                ]
            else:
                prefs["CabinPref"] = [{"Cabin": cabin_req, "PreferLevel": "Only"}]

        # Sabre BFM v5: PriceRequestInformation belongs under TravelerInfoSummary.
        # NegotiatedFareCode must match pattern [A-Za-z]{3}[0-9]{2} (e.g. "ABC12").
        _neg_fare_pattern = re.compile(r'^[A-Za-z]{3}[0-9]{2}$')

        if search_params.corporate_code or search_params.account_code or search_params.currency:
            price_req = rq["TravelerInfoSummary"].setdefault("PriceRequestInformation", {})

            if search_params.currency:
                price_req["CurrencyCode"] = search_params.currency

            if search_params.corporate_code:
                if _neg_fare_pattern.match(search_params.corporate_code):
                    price_req.setdefault("NegotiatedFareCode", []).append(
                        {"Code": search_params.corporate_code}
                    )
                else:
                    print(f"[WARN] corporate_code '{search_params.corporate_code}' does not match "
                          f"Sabre pattern [A-Za-z]{{3}}[0-9]{{2}} — skipped.")

            if search_params.account_code:
                price_req.setdefault("AccountCode", []).append({"Code": search_params.account_code})

        # Return flight for round-trip (not applicable for multi-city)
        if trip_type != "multi_city" and search_params.return_date:
            rq["OriginDestinationInformation"].append({
                "RPH": str(len(rq["OriginDestinationInformation"]) + 1),
                "DepartureDateTime": search_params.return_date + "T00:00:00",
                "OriginLocation": {"LocationCode": search_params.destination.upper()},
                "DestinationLocation": {"LocationCode": search_params.origin.upper()}
            })

        ptq = rq["TravelerInfoSummary"]["AirTravelerAvail"][0]["PassengerTypeQuantity"]
        if search_params.children > 0:
            ptq.append({"Code": "CNN", "Quantity": search_params.children})
        if search_params.infants > 0:
            ptq.append({"Code": "INF", "Quantity": search_params.infants})

        return self._post(SabreEndpoints.BARGAIN_FINDER_MAX, payload, "Flight search", timeout=60)

    def price_flight(self, pricing_params: FlightPricingRequest) -> dict:
        """
        Calls Sabre's Flight Check API to revalidate price and availability.
        """
        flights = []
        last_mktg = ""
        for segment in pricing_params.flight_segments:
            p = _parse_sabre_segment(segment)
            mktg = p["marketing_airline"] or last_mktg
            if mktg:
                last_mktg = mktg
            flight_obj = {
                "departureDate": p["departure_date"],
                "departureTime": p["departure_time"],
                "departureAirportCode": p["origin"],
                "arrivalDate": p["arrival_date"],
                "arrivalTime": p["arrival_time"],
                "arrivalAirportCode": p["destination"],
                "marketingAirlineCode": mktg,
                "marketingFlightNumber": p["flight_number_int"],
                "bookingClass": p["booking_class"]
            }
            if p.get("operating_airline"):
                flight_obj["operatingAirlineCode"] = p["operating_airline"]
            flights.append(flight_obj)

        travelers = []
        for p in pricing_params.passengers:
            for _ in range(p.quantity):
                travelers.append({"passengerTypeCode": _sabre_ptc(p.passenger_type)})

        payload = {"journeys": [{"flights": flights}], "travelers": travelers}
        return self._post(SabreEndpoints.FLIGHT_CHECK, payload, "Flight pricing revalidation")

    # ── Booking ──────────────────────────────────────────────────────────────

    def create_pnr(self, booking_params: FlightBookingRequest) -> dict:
        """
        Calls Sabre's Create Passenger Name Record API to lock in the booking reservation.

        Infants (INF) are added as lap infants: flagged on the name, excluded from
        NumberInParty, and linked to an adult with an INFT SSR.
        """
        person_names = []
        contact_numbers = []
        advance_passengers = []
        secure_flight = []
        services = []

        adult_name_numbers = [
            f"{i+1}.1" for i, p in enumerate(booking_params.passengers) if _sabre_ptc(p.passenger_type) == "ADT"
        ]
        infant_idx = 0
        for i, passenger in enumerate(booking_params.passengers):
            name_number = f"{i+1}.1"
            ptc = _sabre_ptc(passenger.passenger_type)
            is_infant = ptc == "INF"
            first = passenger.first_name.upper()
            last = passenger.last_name.upper()

            name = {"NameNumber": name_number, "GivenName": first, "Surname": last, "PassengerType": ptc}
            if is_infant:
                name["Infant"] = True
            person_names.append(name)

            if passenger.phone:
                contact_numbers.append({"Phone": passenger.phone, "PhoneUseType": "A"})

            gender = "M" if passenger.gender.upper().startswith("M") else "F"
            if is_infant:
                gender += "I"   # MI / FI — infant gender codes for DOCS / Secure Flight

            sf_name = {
                "NameNumber": name_number,
                "GivenName": first,
                "Surname": last,
                "DateOfBirth": passenger.date_of_birth,
                "Gender": gender,
            }
            secure_flight.append({"PersonName": sf_name})

            # DOCS only when a real travel document was provided — never send placeholder passports
            if passenger.document_number:
                advance_passengers.append({
                    "PersonName": sf_name,
                    "Document": {
                        "Number": passenger.document_number.upper(),
                        "IssueCountry": (passenger.document_issue_country or passenger.nationality or "BD").upper()[:2],
                        "NationalityCountry": (passenger.nationality or passenger.document_issue_country or "BD").upper()[:2],
                        "ExpirationDate": passenger.document_expiry,
                        "Type": "P"  # P = Passport
                    }
                })

            if is_infant:
                # Link the infant to an adult (1st infant → 1st adult, ...). Schema guarantees infants <= adults.
                parent = adult_name_numbers[infant_idx] if infant_idx < len(adult_name_numbers) else "1.1"
                dob = datetime.date.fromisoformat(passenger.date_of_birth).strftime("%d%b%y").upper()
                services.append({
                    "SSR_Code": "INFT",
                    "PersonName": {"NameNumber": parent},
                    "Text": f"{last}/{first}/{dob}",
                    "SegmentNumber": "A",
                })
                infant_idx += 1

        seated = sum(1 for p in booking_params.passengers if _sabre_ptc(p.passenger_type) != "INF")

        flight_segments = []
        for segment in booking_params.flight_segments:
            p = _parse_sabre_segment(segment)
            flight_no = str(p["flight_number_int"] or p["flight_number_str"])
            flight_segments.append({
                "DepartureDateTime": p["departure_datetime"],
                "FlightNumber": flight_no,
                "NumberInParty": str(seated),
                "ResBookDesigCode": p["booking_class"],
                "Status": "NN",
                "DestinationLocation": {"LocationCode": p["destination"]},
                "MarketingAirline": {"Code": p["marketing_airline"], "FlightNumber": flight_no},
                "OriginLocation": {"LocationCode": p["origin"]}
            })

        customer_info = {"PersonName": person_names}
        if contact_numbers:
            customer_info["ContactNumbers"] = {"ContactNumber": contact_numbers}

        pax_types_count: Dict[str, int] = {}
        for p in booking_params.passengers:
            ptc = _sabre_ptc(p.passenger_type)
            pax_types_count[ptc] = pax_types_count.get(ptc, 0) + 1

        optional_qualifiers: dict = {
            "PricingQualifiers": {
                "PassengerType": [{"Code": c, "Quantity": str(n)} for c, n in pax_types_count.items()]
            }
        }
        optional_qualifiers.update(_validating_carrier_qualifier(booking_params.validating_carrier))

        payload = {
            "CreatePassengerNameRecordRQ": {
                "version": "2.4.0",
                # Without this Sabre commits the PNR even when AirPrice fails, leaving an unpriced
                # booking with no PQ that can never be ticketed.
                "haltOnAirPriceError": True,
                "TravelItineraryAddInfo": {
                    "AgencyInfo": {"Ticketing": {"TicketType": "7TAW"}},
                    "CustomerInfo": customer_info
                },
                "AirBook": {
                    "OriginDestinationInformation": {"FlightSegment": flight_segments}
                },
                "AirPrice": [
                    {
                        "PriceRequestInformation": {
                            "Retain": True,
                            "OptionalQualifiers": optional_qualifiers
                        }
                    }
                ],
                "SpecialReqDetails": {
                    "SpecialService": {
                        "SpecialServiceInfo": {
                            "SecureFlight": secure_flight,
                            **({"AdvancePassenger": advance_passengers} if advance_passengers else {}),
                            **({"Service": services} if services else {}),
                        }
                    }
                },
                "PostProcessing": {
                    "EndTransaction": {"Source": {"ReceivedFrom": "API"}}
                }
            }
        }

        print(f"[CreatePNR] Sending PNR creation request to Sabre ({len(flight_segments)} segs, "
              f"{len(person_names)} pax)", flush=True)

        try:
            res_data = self._post(SabreEndpoints.CREATE_PNR + "?mode=create", payload, "PNR creation",
                                  timeout=90, unknown_outcome_on_timeout=True)
        except SupplierError:
            # Start the next attempt with a fresh Sabre session
            self._invalidate_token()
            raise

        status = res_data.get("CreatePassengerNameRecordRS", {}).get("ApplicationResults", {}).get("status")
        if status != "Complete":
            self._invalidate_token()
        return res_data

    def extract_booked_price(self, response: dict) -> dict:
        """Fare Sabre stored in the PNR at booking (AirPrice Retain=true)."""
        return extract_sabre_price_quote(response)

    def _stored_fare(self, pnr: str) -> dict:
        """Active stored price quote(s) on the PNR, read with getBooking (read-only)."""
        booking = self._post(SabreEndpoints.GET_PNR_DETAILS, {"confirmationId": pnr}, "PNR retrieval")
        return extract_booking_fares(booking)

    def reprice_pnr(self, pnr: str, passenger_types: list = None, validating_carrier: str = None) -> dict:
        """
        Re-prices the itinerary on an existing PNR (Update Passenger Name Record, AirPrice Retain=true)
        and returns the resulting stored fare. Use when the stored price quote has expired.

        Returns: success, message, pricing {total_fare, base_fare, tax_amount, currency, quote_numbers},
        raw_response.
        """
        if not passenger_types:
            passenger_types = [{"Code": "ADT", "Quantity": "1"}]
        passenger_types = [
            {"Code": _sabre_ptc(pt.get("Code") or pt.get("code")), "Quantity": str(pt.get("Quantity") or pt.get("quantity") or 1)}
            for pt in passenger_types
        ]

        optional_qualifiers: dict = {"PricingQualifiers": {"PassengerType": passenger_types}}
        optional_qualifiers.update(_validating_carrier_qualifier(validating_carrier))

        payload = {
            "UpdatePassengerNameRecordRQ": {
                "version": "1.1.0",
                "Itinerary": {"id": pnr},
                "AirPrice": [
                    {
                        "PriceRequestInformation": {
                            "Retain": True,
                            "OptionalQualifiers": optional_qualifiers
                        }
                    }
                ],
                "PostProcessing": {
                    "EndTransaction": {"Source": {"ReceivedFrom": f"{self.pcc} REPRICE"}}
                }
            }
        }

        print(f"[Reprice] Repricing PNR {pnr}", flush=True)
        res_data = self._post(SabreEndpoints.UPDATE_PNR, payload, "PNR reprice", timeout=60)

        app_status = res_data.get("UpdatePassengerNameRecordRS", {}).get("ApplicationResults", {}).get("status")
        if app_status != "Complete":
            raise SupplierError(f"PNR reprice failed for {pnr} | Details: {json.dumps(res_data)}")

        pricing = self._stored_fare(pnr)
        if not pricing["total_fare"]:
            pricing = extract_sabre_price_quote(res_data)
        return {
            "success": True,
            "message": "PNR repriced successfully",
            "pricing": {**pricing, "quote_number": (pricing["quote_numbers"] or [None])[-1]},
            "raw_response": res_data,
        }

    # ── Ticketing ────────────────────────────────────────────────────────────

    def quote_issue(self, pnr: str, passenger_types: list = None, validating_carrier: str = None) -> dict:
        """
        Re-reads the stored price quote(s) on the PNR before ticketing — this is the fare the airline
        honours at issuance while the PQ is valid. Returns the uniform quote dict used by the price guard.
        """
        pricing = self._stored_fare(pnr)
        if not pricing["total_fare"] or not pricing["quote_numbers"]:
            raise SupplierError(
                f"PNR {pnr} has no active stored price quote (PQ) — it is missing or expired. "
                f"Reprice the PNR (/pnr/reprice) and confirm the new fare before issuing."
            )
        return {
            "amount": pricing["total_fare"], "base": pricing["base_fare"], "tax": pricing["tax_amount"],
            "currency": pricing["currency"], "context": {"quote_numbers": pricing["quote_numbers"]},
        }

    def issue_ticket(self, ticketing_params: TicketingRequest, quote: dict) -> dict:
        """
        Issues e-tickets for the given PNR against the price quote record(s) from quote_issue().

        quote_issue() re-reads the active stored PQ(s) and the price guard confirms that amount first;
        exactly those PQ records are ticketed. Commission comes from the supplier configuration
        (settings.commission_percent), never from the API caller.

        DesignatePrinter notes (Sabre REST AirTicketRQ v1.3.0):
          - Ticket.CountryCode : BSP/ARC country for settlement — LNIATA is invalid on this node.
          - Hardcopy / InvoiceItinerary LNIATA: optional, only sent when configured.
        """
        quote_numbers = ((quote or {}).get("context") or {}).get("quote_numbers") or [1]
        payload = self._air_ticket_payload(
            ticketing_params.pnr, [{"Number": int(n)} for n in quote_numbers],
            fop_type=ticketing_params.fop_type, country=ticketing_params.country_code,
            printer=ticketing_params.printer_id,
        )
        print(f"[Issue] Ticketing PNR {ticketing_params.pnr} with PQ records {quote_numbers}", flush=True)
        return self._post(SabreEndpoints.ISSUE_TICKET, payload, "Ticketing",
                          timeout=120, unknown_outcome_on_timeout=True)

    def _air_ticket_payload(self, pnr: str, records: list, fop_type: Optional[str] = None,
                            country: Optional[str] = None, printer: Optional[str] = None) -> dict:
        """AirTicketRQ v1.3.0 for the given PQ records (or PQR records with Reissue=true)."""
        lniata = printer or self.lniata
        printers: dict = {"Ticket": {"CountryCode": country or self.config.country_code or "BD"}}
        if lniata:
            printers["Hardcopy"] = {"LNIATA": lniata}
            printers["InvoiceItinerary"] = {"LNIATA": lniata}

        ticketing: dict = {
            "FOP_Qualifiers": {"BasicFOP": {"Type": fop_type or "CA"}},
            "PricingQualifiers": {"PriceQuote": [{"Record": records}]},
        }
        commission = (self.config.settings or {}).get("commission_percent", 7)
        if commission is not None:
            ticketing["MiscQualifiers"] = {"Commission": {"Percent": float(commission)}}

        return {
            "AirTicketRQ": {
                "version": "1.3.0",
                "DesignatePrinter": {"Printers": printers},
                "Itinerary": {"ID": pnr},
                "Ticketing": [ticketing],
                "PostProcessing": {
                    "EndTransaction": {"Source": {"ReceivedFrom": f"{self.pcc} WEB"}}
                }
            }
        }

    def get_pnr_details(self, details_params: PNRDetailsRequest) -> dict:
        return self._post(SabreEndpoints.GET_PNR_DETAILS, {"confirmationId": details_params.pnr}, "PNR retrieval")

    def cancel_itinerary(self, cancel_params: CancelItineraryRequest) -> dict:
        payload = {
            "confirmationId": cancel_params.pnr,
            "cancelAll": cancel_params.cancel_segments if cancel_params.cancel_segments is not None else True
        }
        return self._post(SabreEndpoints.CANCEL_ITINERARY, payload, "Itinerary cancellation",
                          unknown_outcome_on_timeout=True)

    def void_ticket(self, void_params: VoidTicketRequest) -> dict:
        payload = {"tickets": [void_params.ticket_number], "confirmationId": void_params.pnr}
        return self._post(SabreEndpoints.VOID_TICKET, payload, "Ticket voiding",
                          unknown_outcome_on_timeout=True)

    # ── Exchange / Refund ────────────────────────────────────────────────────

    # Sabre automated exchange (Exchange Booking REST v1.1.0):
    #   quote   → ExchangeBooking with a price comparison that always halts (amountSpecified=-1, zero
    #             tolerance): Sabre prices the exchange but commits nothing.
    #   confirm → ExchangeBooking with amountSpecified=<confirmed amount> and halt on any increase
    #             beyond tolerance: Sabre rebooks, stores the PQR and commits only within the price;
    #             then AirTicketRQ with PriceQuote Record=<PQR>, Reissue=true issues the new ticket.

    def _exchange_context(self, pnr: str, ticket_number: str) -> dict:
        """Segments covered by the ticket (by PNR segment number) and the ticket holder's name number."""
        booking = self._post(SabreEndpoints.GET_PNR_DETAILS, {"confirmationId": pnr}, "PNR retrieval")
        ticket = next((t for t in _as_list(booking.get("flightTickets")) if t.get("number") == ticket_number), None)
        if not ticket:
            raise ValueError(f"Ticket {ticket_number} is not on PNR {pnr}")
        if str(ticket.get("ticketStatusCode") or "").upper() not in ("TE", "TKT", "E") and \
                str(ticket.get("ticketStatusName") or "").lower() != "issued":
            raise ValueError(f"Ticket {ticket_number} is {ticket.get('ticketStatusName')} — only an issued ticket can be exchanged")

        flights = [f for f in _as_list(booking.get("flights")) if isinstance(f, dict)]
        flights.sort(key=lambda f: (str(f.get("departureDate")), str(f.get("departureTime"))))
        open_items = {
            str(c.get("itemId")) for c in _as_list(ticket.get("flightCoupons"))
            if str(c.get("couponStatusCode") or "I").upper() in ("I", "O", "A")
        }
        segments = [i + 1 for i, f in enumerate(flights) if str(f.get("itemId")) in open_items]
        if not segments:
            raise ValueError(f"Ticket {ticket_number} has no open coupons left to exchange")

        traveler_index = ticket.get("travelerIndex")
        travelers = [t for t in _as_list(booking.get("travelers")) if isinstance(t, dict)]
        holder = next((t for t in travelers if t.get("travelerIndex") == traveler_index), None) or \
            (travelers[0] if len(travelers) == 1 else None)
        name_number = f"{(holder or {}).get('nameAssociationId') or traveler_index or 1}.1"
        seated = sum(1 for t in travelers if str(t.get("passengerCode") or t.get("type") or "ADT").upper() != "INF") or 1
        return {"segments": segments, "name_number": name_number, "seated": seated}

    def _exchange_booking(self, pnr: str, ticket_number: str, new_segments: list, ctx: dict,
                          amount_specified: float, increase_tolerance: float, halt_on_decrease: bool) -> dict:
        flight_segments = []
        for seg in new_segments:
            p = _parse_sabre_segment(seg)
            flight_no = str(p["flight_number_int"] or p["flight_number_str"])
            flight_segments.append({
                "DepartureDateTime": p["departure_datetime"],
                "ArrivalDateTime": p["arrival_datetime"],
                "FlightNumber": flight_no,
                "NumberInParty": str(ctx["seated"]),
                "ResBookDesigCode": p["booking_class"],
                "Status": "NN",
                "OriginLocation": {"LocationCode": p["origin"]},
                "DestinationLocation": {"LocationCode": p["destination"]},
                "MarketingAirline": {"Code": p["marketing_airline"], "FlightNumber": flight_no},
            })

        payload = {"ExchangeBookingRQ": {
            "version": "1.1.0",
            "Itinerary": {"id": pnr},
            "Cancel": {"Segment": [{"Number": n} for n in ctx["segments"]]},
            "AirBook": {
                # Halt (change nothing) unless every new segment is confirmed by the airline
                "HaltOnStatus": [{"Code": c} for c in ("HL", "KK", "LL", "NN", "NO", "UC", "US")],
                "OriginDestinationInformation": {"FlightSegment": flight_segments},
            },
            "AutomatedExchanges": [{
                "ExchangeComparison": {
                    "OriginalTicketNumber": ticket_number,
                    "PriceRequestInformation": {"OptionalQualifiers": {"PricingQualifiers": {
                        "NameSelect": {"NameNumber": ctx["name_number"]}}}},
                },
                "PriceComparison": {
                    "amountSpecified": amount_specified,
                    "AcceptablePriceIncrease": {"haltOnNonAcceptablePrice": True, "Amount": increase_tolerance},
                    "AcceptablePriceDecrease": {"haltOnNonAcceptablePrice": halt_on_decrease, "Amount": 0},
                },
            }],
            "PostProcessing": {
                "returnPQRInfo": True,
                "redisplayReservation": False,
                "EndTransaction": {"Source": {"ReceivedFrom": f"{self.pcc} EXCHANGE"}},
            },
        }}
        try:
            res = self._post(SabreEndpoints.EXCHANGE_BOOKING, payload, "Exchange pricing",
                             timeout=120, unknown_outcome_on_timeout=True)
        finally:
            # Exchange Booking runs in the token's Sabre session — start the next call clean
            self._invalidate_token()
        return res.get("ExchangeBookingRS", res)

    @staticmethod
    def _parse_exchange_result(rs: dict) -> dict:
        app = rs.get("ApplicationResults") or {}
        messages = _sabre_messages(app)
        confirmation = next(iter(_as_list(rs.get("ExchangeConfirmation"))), {}) or {}
        pqr = confirmation.get("PQR_Number") or next(
            (q.get("PQR_Number") for q in _as_list(rs.get("PriceQuoteReissue")) if isinstance(q, dict)), None)

        returned = next((v for v in _find_all(rs, "amountReturned") if v not in (None, "")), None)
        details = next(iter(_find_all(rs, "ExchangeDetails")), {}) or {}
        details = details[0] if isinstance(details, list) and details else details
        change_fee = sum(_to_float(c.get("Amount")) for c in _as_list(details.get("ChangeFeeInformation")) if isinstance(c, dict))
        fare_diff = sum(_to_float(t.get("Amount")) for t in _as_list(details.get("TransactionInformation")) if isinstance(t, dict))
        total_node = next(iter(_find_all(rs, "TotalFare")), {}) or {}
        currency = details.get("CurrencyCode") or (total_node.get("CurrencyCode") if isinstance(total_node, dict) else None)
        amount = _to_float(returned) if returned is not None else (fare_diff + change_fee if details else None)
        return {
            "status": app.get("status"),
            "messages": messages,
            "pqr_number": int(_to_float(pqr)) if pqr else None,
            "amount": round(amount, 2) if amount is not None else None,
            "currency": currency,
            "breakdown": {
                "fare_difference": round(fare_diff, 2),
                "change_fee": round(change_fee, 2),
                "ticket_value": _to_float(details.get("TicketValue")) or None,
                "new_fare_total": _to_float(total_node.get("Amount")) if isinstance(total_node, dict) else None,
            },
        }

    @staticmethod
    def _raise_exchange_blocker(result: dict, action: str) -> None:
        text = " | ".join(result["messages"]) or "no details returned"
        upper = text.upper()
        if "ENTRY NOT AVAILABLE" in upper or "NOT AUTHORIZED" in upper or "NOT ACTIVE" in upper:
            raise SupplierError(
                f"{action}: Sabre Automated Exchanges (WFR) is not activated for this PCC — Sabre must enable it "
                f"before tickets can be reissued through the API. Nothing was changed. | Details: {text}"
            )
        if any(code in upper for code in ("HALT ON STATUS", "UNABLE TO SELL", "NO AVAIL", "UC ", "NN ")):
            raise SupplierError(f"{action}: the new flight could not be confirmed by the airline. Nothing was changed. | Details: {text}")
        raise SupplierError(f"{action} failed. Nothing was changed. | Details: {text}")

    def quote_exchange(self, params: ExchangeQuoteRequest, passenger_types: Optional[list] = None,
                       keep_open: bool = False) -> dict:
        """
        Prices the exchange without committing anything (price comparison always halts).
        Returns: amount (to collect), currency, breakdown, context.
        """
        ctx = self._exchange_context(params.pnr, params.original_ticket_number)
        rs = self._exchange_booking(params.pnr, params.original_ticket_number, params.new_flight_segments, ctx,
                                    amount_specified=-1, increase_tolerance=0, halt_on_decrease=True)
        result = self._parse_exchange_result(rs)

        if result["pqr_number"] and result["status"] == "Complete":
            # Price happened to equal the sentinel and Sabre committed: the exchange is already stored
            ctx["pqr_number"] = result["pqr_number"]
        elif result["amount"] is None:
            self._raise_exchange_blocker(result, "Exchange quote")

        return {
            "amount": result["amount"],
            "currency": result["currency"],
            "breakdown": {**result["breakdown"], "warnings": result["messages"]},
            "context": ctx,
        }

    def release_quote(self, quote: Optional[dict]) -> None:
        """Sabre quotes hold no supplier session — nothing to release."""

    def exchange_ticket(self, params: ExchangeTicketRequest, quote: dict) -> dict:
        """
        Commits the exchange within the confirmed amount (Sabre-side price guard), then reissues the
        ticket against the stored PQR. If the reissue fails after the PQR was stored, raises
        PartialExchangeError so the next confirm retries only the reissue.
        """
        ctx = quote.get("context") or {}
        pqr = ctx.get("pqr_number")
        if not pqr:
            rs = self._exchange_booking(
                params.pnr, params.original_ticket_number, ctx["new_flight_segments"], ctx,
                amount_specified=float(params.confirmed_amount), increase_tolerance=float(ctx.get("tolerance", 1)),
                halt_on_decrease=False,
            )
            result = self._parse_exchange_result(rs)
            if not result["pqr_number"] or result["status"] != "Complete":
                if result["amount"] is not None and result["amount"] > float(params.confirmed_amount) + float(ctx.get("tolerance", 1)):
                    raise PriceChangedError(
                        f"Exchange price increased to {result['currency']} {result['amount']}. Nothing was changed.",
                        {"amount": result["amount"], "currency": result["currency"], "breakdown": result["breakdown"]},
                    )
                self._raise_exchange_blocker(result, "Exchange commit")
            pqr = result["pqr_number"]

        payload = self._air_ticket_payload(params.pnr, [{"Number": int(pqr), "Reissue": True}])
        try:
            res = self._post(SabreEndpoints.ISSUE_TICKET, payload, "Reissue",
                             timeout=120, unknown_outcome_on_timeout=True)
        except SupplierError as exc:
            raise PartialExchangeError(
                f"The itinerary was changed and reissue record PQR {pqr} is stored, but the new ticket was not "
                f"issued. Retry /ticket/exchange with the same quote_id to reissue only, or reissue PQR {pqr} in "
                f"Sabre Red. Do NOT request a new quote. | Details: {exc}", pqr_number=pqr) from exc

        rs = res.get("AirTicketRS", {})
        if (rs.get("ApplicationResults") or {}).get("status") != "Complete":
            raise PartialExchangeError(
                f"The itinerary was changed and PQR {pqr} is stored, but Sabre did not reissue the ticket: "
                f"{' | '.join(_sabre_messages(rs.get('ApplicationResults') or {})) or 'no details'}. "
                f"Retry /ticket/exchange with the same quote_id, or reissue PQR {pqr} in Sabre Red.", pqr_number=pqr)

        tickets = [
            {"TicketNumber": str(t.get("DocumentNumber") or t.get("TicketNumber"))}
            for t in _as_list(rs.get("Summary")) if isinstance(t, dict) and (t.get("DocumentNumber") or t.get("TicketNumber"))
        ]
        return {"status": "Success", "pnr": params.pnr, "pqr_number": pqr, "TicketDetails": tickets, "raw_response": res}

    def quote_refund(self, params: RefundQuoteRequest) -> dict:
        """
        Prices a refund via Booking Management checkFlightTickets (read-only — nothing is changed).
        Returns: refundable, amount, currency, penalty, tickets[], raw_response.
        """
        payload = {"tickets": [{"number": t} for t in params.ticket_numbers]}
        res = self._post(SabreEndpoints.CHECK_FLIGHT_TICKETS, payload, "Refund quote")

        tickets, amount, penalty, currency = [], 0.0, 0.0, None
        refundable = True
        for node in _find_all(res, "refundTotals"):
            if not isinstance(node, dict):
                continue
            amount += _to_float(node.get("total"))
            currency = currency or node.get("currencyCode")
        for pen in _find_all(res, "refundPenalties"):
            for p in _as_list(pen):
                if isinstance(p, dict):
                    # {"applicability": "BEFORE_DEPARTURE", "penalty": {"amount": "18531.0", "currencyCode": "BDT"}}
                    node = p.get("penalty") if isinstance(p.get("penalty"), dict) else p
                    penalty += _to_float(node.get("amount") or node.get("total"))
                    currency = currency or node.get("currencyCode")
        flags = _find_all(res, "isRefundable")
        if not flags or not all(bool(f) for f in flags):
            refundable = False
        for t in _find_all(res, "number"):
            if isinstance(t, str) and t.isdigit() and len(t) == 13 and t not in tickets:
                tickets.append(t)

        # Sabre explains blockers as warnings, e.g. "49005: Automated Refunds not active"
        warnings = [e.get("description") for e in _as_list(res.get("errors")) if isinstance(e, dict) and e.get("description")]
        priced = bool(_find_all(res, "refundTotals"))
        reason = None
        if not refundable:
            reason = "Ticket is not refundable per the fare rules"
        elif not priced:
            reason = "Sabre did not price the refund" + (f": {'; '.join(warnings)}" if warnings else "")

        return {
            "refundable": refundable and priced,
            "amount": round(amount, 2),
            "penalty": round(penalty, 2),
            "currency": currency,
            "tickets": tickets or list(params.ticket_numbers),
            "reason": reason,
            "warnings": warnings,
            "raw_response": res,
        }

    def refund_ticket(self, params: RefundTicketRequest, quote: dict) -> dict:
        """
        Submits the refund via Booking Management refundFlightTickets. Called only after the
        controller re-quoted with quote_refund() and the price guard accepted the amount.
        """
        payload: dict = {"tickets": [{"number": t} for t in params.ticket_numbers]}
        if params.waiver_code:
            payload["refundQualifiers"] = {"waiverCode": params.waiver_code}
        return self._post(SabreEndpoints.REFUND_FLIGHT_TICKETS, payload, "Ticket refund",
                          timeout=90, unknown_outcome_on_timeout=True)

    # ── Ancillaries ──────────────────────────────────────────────────────────

    def get_seat_maps(self, seat_params: SeatMapRequest) -> dict:
        """Get Seats, payload request: seat map and seat prices for one flight segment."""
        p = _parse_sabre_segment(seat_params.flight_segment)
        segment = {
            "paxSegmentId": "SEG1",
            "departure": {"locationCode": p["origin"], "aircraftScheduledDate": {"date": p["departure_date"]}},
            "arrival": {"locationCode": p["destination"]},
            "marketingCarrierInfo": {
                "carrierCode": p["marketing_airline"],
                "carrierFlightNumber": str(p["flight_number_int"] or p["flight_number_str"]),
                "bookingCode": p["booking_class"],
            },
        }
        payload = {
            "requestType": "payload",
            "request": {
                "paxes": [{"paxID": "PAX1", "ptc": "ADT"}],
                "originDest": {"paxJourney": {"paxSegments": [segment]}},
                "paxSegmentRefIds": ["SEG1"],
            },
        }
        res = self._post(SabreEndpoints.GET_SEATS, payload, "Seat map retrieval")
        if not (res.get("response") or {}).get("seatMaps"):
            errors = res.get("errors") or [{}]
            raise SupplierError(f"Seat map retrieval failed: {errors[0].get('descriptionText') or 'no seat map returned'}")
        return res

    def get_baggage_allowance(self, baggage_params: BaggageAllowanceRequest) -> dict:
        """The booking itself carries the allowance (getBooking → fareOffers)."""
        return self.get_pnr_details(PNRDetailsRequest(pnr=baggage_params.pnr))

    def place_in_queue(self, queue_params: QueueRequest) -> dict:
        payload = {
            "QueuePlaceRQ": {
                "version": "1.0.0",
                "QueueInfo": {
                    "QueueIdentifier": [
                        {"Number": queue_params.queue_number, "PseudoCityCode": queue_params.pseudo_city_code}
                    ],
                    "RecordLocator": queue_params.pnr
                }
            }
        }
        return self._post(SabreEndpoints.QUEUE_PLACE, payload, "Queue placement")

    def get_fare_rules(self, rules_params: FareRulesRequest) -> dict:
        """Change / refund penalties of a booked fare (getBooking → fareRules)."""
        if not rules_params.pnr:
            raise OperationNotSupportedError(
                "Sabre returns fare rules for booked PNRs only — send 'pnr'. Rules before booking need "
                "Sabre's SOAP fare-rules service, which this integration does not use."
            )
        return self.get_pnr_details(PNRDetailsRequest(pnr=rules_params.pnr))
