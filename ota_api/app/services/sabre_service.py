import json
import re
import requests
from app.services.sabre_auth_service import SabreBaseService
from app.models.flight_schemas import (
    FlightSearchRequest, FlightPricingRequest, FlightBookingRequest, TicketingRequest,
    PNRDetailsRequest, CancelItineraryRequest, VoidTicketRequest, ExchangeTicketRequest,
    SeatMapRequest, BaggageAllowanceRequest, QueueRequest, FareRulesRequest
)
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


class SabreFlightService(SabreBaseService):


    
    def __init__(self, config: Optional[SupplierConfig] = None):
        super().__init__(config=config)

    
    def search_flights(self, search_params: FlightSearchRequest) -> dict:
        """
        Calls Sabre's Bargain Finder Max (BFM) API to search for flights.
        """
        url = f"{self.base_url}{SabreEndpoints.BARGAIN_FINDER_MAX}"
        headers = self.get_headers()
        
        # BFM Request Payload Structure Construction
        # This is a minimal basic structure for connecting.

        # ── Build OriginDestinationInformation ─────────────────────────────
        origin_dest_info = []
        trip_type = (search_params.trip_type or "one_way").lower()

        if trip_type == "multi_city" and search_params.segments:
            for idx, seg in enumerate(search_params.segments):
                origin_dest_info.append({
                    "RPH": str(idx + 1),
                    "DepartureDateTime": seg.departure_date + "T00:00:00",
                    "OriginLocation": {
                        "LocationCode": seg.origin.upper()
                    },
                    "DestinationLocation": {
                        "LocationCode": seg.destination.upper()
                    }
                })
        else:
            origin_dest_info.append({
                "RPH": "1",
                "DepartureDateTime": search_params.departure_date + "T00:00:00",
                "OriginLocation": {
                    "LocationCode": search_params.origin
                },
                "DestinationLocation": {
                    "LocationCode": search_params.destination
                }
            })

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
                                "CompanyName": {
                                    "Code": "TN"
                                }
                            }
                        }
                    ]
                },
                "OriginDestinationInformation": origin_dest_info,
                "TravelerInfoSummary": {
                    "SeatsRequested": [search_params.adults + search_params.children + search_params.infants],
                    "AirTravelerAvail": [
                        {
                            "PassengerTypeQuantity": [
                                {
                                    "Code": "ADT", 
                                    "Quantity": search_params.adults
                                }
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
        
        # Reference shortcuts for cleaner code
        tpa_extensions = payload["OTA_AirLowFareSearchRQ"]["TPA_Extensions"]
        
        # 1. Flexible Dates (+/- 1 to 3 days)
        if search_params.flexible_dates:
             # Changes the request to ADRC (Alternate Date Request)
             tpa_extensions["IntelliSellTransaction"]["RequestType"]["Name"] = "ADRC"
             
        # 2. Direct Flights & Max Stops
        if search_params.direct_flights_only or search_params.max_stops is not None:
            stop_qty = 0 if search_params.direct_flights_only else search_params.max_stops

            if "TravelPreferences" not in payload["OTA_AirLowFareSearchRQ"]:
                payload["OTA_AirLowFareSearchRQ"]["TravelPreferences"] = {}
            payload["OTA_AirLowFareSearchRQ"]["TravelPreferences"]["MaxStopsQuantity"] = stop_qty

        # 3. Included & Excluded Airlines
        if search_params.included_airlines or search_params.excluded_airlines:
             if "TravelPreferences" not in payload["OTA_AirLowFareSearchRQ"]:
                  payload["OTA_AirLowFareSearchRQ"]["TravelPreferences"] = {}
             
             vendor_prefs = []
             if search_params.included_airlines:
                  for airline in search_params.included_airlines:
                       vendor_prefs.append({"Code": airline, "Type": "Marketing"})
             
             if search_params.excluded_airlines:
                  for airline in search_params.excluded_airlines:
                       # Sabre uses an Exclude flag or PreferLevel="Unacceptable" depending on soap/rest schema. 
                       # For BFM REST standard it's often an Exclude attribute.
                       vendor_prefs.append({"Code": airline, "Type": "Marketing", "Exclude": True})
                       
             payload["OTA_AirLowFareSearchRQ"]["TravelPreferences"]["VendorPref"] = vendor_prefs

        # 3.5 Cabin Class Preference
        if search_params.cabin_class:
             cabin_req = search_params.cabin_class.upper()
             
             if "TravelPreferences" not in payload["OTA_AirLowFareSearchRQ"]:
                  payload["OTA_AirLowFareSearchRQ"]["TravelPreferences"] = {}
             
             if cabin_req == "ALL":
                  # To get a mix of cabins, provide all as Preferred, though BFM still optimizes for lowest fare
                  payload["OTA_AirLowFareSearchRQ"]["TravelPreferences"]["CabinPref"] = [
                       {"Cabin": "Y", "PreferLevel": "Preferred"},
                       {"Cabin": "S", "PreferLevel": "Preferred"},
                       {"Cabin": "C", "PreferLevel": "Preferred"},
                       {"Cabin": "J", "PreferLevel": "Preferred"},
                       {"Cabin": "F", "PreferLevel": "Preferred"},
                       {"Cabin": "P", "PreferLevel": "Preferred"}
                  ]
             else:
                  # For a specific cabin, enforce it strictly with "Only"
                  payload["OTA_AirLowFareSearchRQ"]["TravelPreferences"]["CabinPref"] = [
                       {
                            "Cabin": cabin_req,
                            "PreferLevel": "Only"
                       }
                  ]
        # Sabre BFM v5: PriceRequestInformation belongs under TravelerInfoSummary.
        # NegotiatedFareCode must match pattern [A-Za-z]{3}[0-9]{2} (e.g. "ABC12").
        _neg_fare_pattern = re.compile(r'^[A-Za-z]{3}[0-9]{2}$')

        if search_params.corporate_code or search_params.account_code or search_params.currency:
            price_req = payload["OTA_AirLowFareSearchRQ"]["TravelerInfoSummary"].setdefault(
                "PriceRequestInformation", {}
            )

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
                price_req.setdefault("AccountCode", []).append(
                    {"Code": search_params.account_code}
                )
        
        # Handle Return flight for round-trip (not applicable for multi-city)
        if trip_type != "multi_city" and search_params.return_date:
             rph = str(len(payload["OTA_AirLowFareSearchRQ"]["OriginDestinationInformation"]) + 1)
             payload["OTA_AirLowFareSearchRQ"]["OriginDestinationInformation"].append({
                 "RPH": rph,
                 "DepartureDateTime": search_params.return_date + "T00:00:00",
                 "OriginLocation": {
                    "LocationCode": search_params.destination
                 },
                 "DestinationLocation": {
                     "LocationCode": search_params.origin
                 }
             })
             
        # Children and Infants dynamic inclusion
        if search_params.children > 0:
            payload["OTA_AirLowFareSearchRQ"]["TravelerInfoSummary"]["AirTravelerAvail"][0]["PassengerTypeQuantity"].append({
                 "Code": "CNN",
                 "Quantity": search_params.children
             })
             
        if search_params.infants > 0:
             payload["OTA_AirLowFareSearchRQ"]["TravelerInfoSummary"]["AirTravelerAvail"][0]["PassengerTypeQuantity"].append({
                 "Code": "INF",
                 "Quantity": search_params.infants
             })
             
        print(f"Sending request to Sabre: {url}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
             error_details = ""
             if 'response' in locals() and hasattr(response, 'text'):
                  error_details = f" | Details: {response.text}"
                  print(f"Sabre Error Response: {response.text}")
             raise Exception(f"Flight search failed. {str(e)}{error_details}")


    def price_flight(self, pricing_params: FlightPricingRequest) -> dict:
        """
        Calls Sabre's Flight Check API to revalidate price and availability.
        """
        url = f"{self.base_url}{SabreEndpoints.FLIGHT_CHECK}"
        headers = self.get_headers()
        
        # Extract and format journeys/flights for Flight Check API v1 (Strict Schema)
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


        # Travelers list (Strict Schema)
        travelers = []
        for p in pricing_params.passengers:
            for _ in range(p.quantity):
                travelers.append({
                    "passengerTypeCode": p.passenger_type
                })

        payload = {
            "journeys": [
                {
                    "flights": flights
                }
            ],
            "travelers": travelers
        }
        
        print(f"Sending Flight Check request to Sabre: {url}", flush=True)
        print(f"Sabre Flight Check Request Payload: {json.dumps(payload, indent=2)}", flush=True)
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}", flush=True)
            raise Exception(f"Flight pricing revalidation failed. {str(e)}{error_details}")
        
    def create_pnr(self, booking_params: FlightBookingRequest) -> dict:
        """
        Calls Sabre's Create Passenger Name Record API to lock in the booking reservation.
        """
        url = f"{self.base_url}{SabreEndpoints.CREATE_PNR}?mode=create"
        headers = self.get_headers()
        
        person_names = []
        contact_numbers = []
        
        advance_passengers = []
        for i, passenger in enumerate(booking_params.passengers):
            name_number = f"{i+1}.1"
            person_names.append({
                "NameNumber": name_number,
                "GivenName": passenger.first_name.upper(),
                "Surname": passenger.last_name.upper()
            })
            
            if passenger.phone:
                contact_numbers.append({
                    "Phone": passenger.phone,
                    "PhoneUseType": "A"
                })
                
            # APIS / Advance Passenger Info for ticketing
            if passenger.date_of_birth and passenger.gender:
                adv_pax = {
                    "PersonName": {
                        "NameNumber": name_number,
                        "GivenName": passenger.first_name.upper(),
                        "Surname": passenger.last_name.upper(),
                        "DateOfBirth": passenger.date_of_birth,
                        "Gender": "M" if passenger.gender.upper().startswith("M") else "F"
                    }
                }
                if passenger.document_number:
                    adv_pax["Document"] = {
                        "Number": passenger.document_number.upper(),
                        "IssueCountry": (passenger.document_issue_country or passenger.nationality or "BD").upper()[:2],
                        "NationalityCountry": (passenger.nationality or passenger.document_issue_country or "BD").upper()[:2],
                        "ExpirationDate": passenger.document_expiry or "2099-12-31",
                        "Type": "P" # P = Passport
                    }
                else:
                    # If document is not provided, we can still try to pass DOCS with a dummy or just DOB/Gender.
                    # Some airlines accept it as SecureFlight (DOCO/DOCA), but for DOCS a document is usually required.
                    adv_pax["Document"] = {
                        "Number": "00000000",
                        "IssueCountry": (passenger.nationality or "BD").upper()[:2],
                        "NationalityCountry": (passenger.nationality or "BD").upper()[:2],
                        "ExpirationDate": "2099-12-31",
                        "Type": "P"
                    }
                advance_passengers.append(adv_pax)
                
        flight_segments = []
        for segment in booking_params.flight_segments:
            p = _parse_sabre_segment(segment)
            num_passengers = str(len(booking_params.passengers))

            flight_segments.append({
                "DepartureDateTime": p["departure_datetime"],
                "FlightNumber": str(p["flight_number_int"] or p["flight_number_str"]),
                "NumberInParty": num_passengers,
                "ResBookDesigCode": p["booking_class"],
                "Status": "NN",
                "DestinationLocation": {
                    "LocationCode": p["destination"]
                },
                "MarketingAirline": {
                    "Code": p["marketing_airline"],
                    "FlightNumber": str(p["flight_number_int"] or p["flight_number_str"])
                },
                "OriginLocation": {
                    "LocationCode": p["origin"]
                }
            })

        customer_info = {
            "PersonName": person_names
        }
        if contact_numbers:
            customer_info["ContactNumbers"] = {
                "ContactNumber": contact_numbers
            }

        # Map passenger types for pricing
        pax_types_count = {}
        for p in booking_params.passengers:
            ptc = p.passenger_type or "ADT"
            pax_types_count[ptc] = pax_types_count.get(ptc, 0) + 1

        pricing_pax_types = []
        for ptc, count in pax_types_count.items():
            pricing_pax_types.append({
                "Code": ptc,
                "Quantity": str(count)
            })

        pricing_qualifiers = {
            "PassengerType": pricing_pax_types
        }

        # Build AirPrice OptionalQualifiers — include FlightQualifiers.ValidatingCarrier when
        # a specific carrier is provided so Sabre's stored Price Quote is bound to a carrier
        # that this PCC has Electronic Ticketing Authority (ETA) for.
        # NOTE: ValidatingCarrier belongs under FlightQualifiers (not PricingQualifiers) in v2.4.0.
        optional_qualifiers: dict = {
            "PricingQualifiers": pricing_qualifiers
        }
        if getattr(booking_params, "validating_carrier", None):
            optional_qualifiers["FlightQualifiers"] = {
                "ValidatingCarrier": {
                    "Code": booking_params.validating_carrier.strip().upper()
                }
            }

        payload = {
            "CreatePassengerNameRecordRQ": {
                "version": "2.4.0",
                "TravelItineraryAddInfo": {
                    "AgencyInfo": {
                        "Ticketing": {
                            "TicketType": "7TAW"
                        }
                    },
                    "CustomerInfo": customer_info
                },
                "AirBook": {
                    "OriginDestinationInformation": {
                        "FlightSegment": flight_segments
                    }
                },
                "AirPrice": [
                    {
                        "PriceRequestInformation": {
                            "Retain": True,
                            "OptionalQualifiers": optional_qualifiers
                        }
                    }
                ],
                "PostProcessing": {
                    "EndTransaction": {
                        "Source": {
                            "ReceivedFrom": "API"
                        }
                    }
                }
            }
        }
        
        if advance_passengers:
            secure_flight = []
            for adv_pax in advance_passengers:
                if "PersonName" in adv_pax:
                    secure_flight.append({
                        "PersonName": adv_pax["PersonName"]
                    })
            payload["CreatePassengerNameRecordRQ"]["SpecialReqDetails"] = {
                "SpecialService": {
                    "SpecialServiceInfo": {
                        "AdvancePassenger": advance_passengers,
                        "SecureFlight": secure_flight
                    }
                }
            }
        
        print(f"Sending PNR creation request to Sabre: {url}", flush=True)
        print(f"Sabre PNR Creation Request Payload: {json.dumps(payload, indent=2)}", flush=True)
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            res_data = response.json()
            
            # If PNR creation was not successful, delete cached token to start the next attempt with a fresh session
            rs = res_data.get("CreatePassengerNameRecordRS", {})
            app_results = rs.get("ApplicationResults", {})
            status = app_results.get("status")
            if status != "Complete":
                try:
                    from app.utils.redis_utils import redis_helper
                    redis_helper.delete_key("sabre_access_token")
                    print("[INFO] Invalidated cached Sabre token due to incomplete PNR creation.", flush=True)
                except Exception as re:
                    print(f"[WARN] Failed to invalidate cached Sabre token: {re}", flush=True)
            return res_data
        except requests.exceptions.RequestException as e:

            try:
                from app.utils.redis_utils import redis_helper
                redis_helper.delete_key("sabre_access_token")
                print("[INFO] Invalidated cached Sabre token due to PNR creation request failure.", flush=True)
            except Exception as re:
                print(f"[WARN] Failed to invalidate cached Sabre token on request exception: {re}", flush=True)
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}", flush=True)
            raise Exception(f"PNR creation failed. {str(e)}{error_details}")

    def reprice_pnr(self, pnr: str, passenger_types: list = None, validating_carrier: str = None) -> dict:
        """
        Reprices / re-generates the price quote on an existing PNR.
        Used when the original price quote has expired.

        Returns both the raw Sabre response and a parsed `pricing` dict with:
          - total_fare, base_fare, tax_amount, currency, quote_number

        :param pnr:                6-character Sabre Record Locator
        :param passenger_types:    list of dicts like [{"Code": "ADT", "Quantity": "1"}]
                                   If None, defaults to 1 adult.
        :param validating_carrier: Optional airline code to force validating carrier on the quote
        :return: dict with keys: raw_response, pricing, success, message
        """
        url = f"{self.base_url}{SabreEndpoints.CREATE_PNR}?mode=reprice"
        headers = self.get_headers()

        if not passenger_types:
            passenger_types = [{"Code": "ADT", "Quantity": "1"}]

        reprice_pricing_qualifiers = {
            "PassengerType": passenger_types
        }
        if validating_carrier:
            reprice_pricing_qualifiers["ValidatingCarrier"] = {
                "Code": validating_carrier.upper()
            }

        payload = {
            "CreatePassengerNameRecordRQ": {
                "version": "2.4.0",
                "TravelItineraryAddInfo": {
                    "AgencyInfo": {
                        "Ticketing": {
                            "TicketType": "7TAW"
                        }
                    }
                },
                "AirPrice": [
                    {
                        "PriceRequestInformation": {
                            "Retain": True,
                            "OptionalQualifiers": {
                                "PricingQualifiers": reprice_pricing_qualifiers
                            }
                        }
                    }
                ],
                "Itinerary": {
                    "ID": pnr
                },
                "PostProcessing": {
                    "EndTransaction": {
                        "Source": {
                            "ReceivedFrom": f"{self.pcc} REPRICE"
                        }
                    }
                }
            }
        }

        print(f"[Reprice] Repricing PNR {pnr} at {url}", flush=True)

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            res_data = response.json()
            print(f"[Reprice] Raw response keys: {list(res_data.keys())}", flush=True)

            # ── Parse pricing from AirPrice section of the response ──────────
            pricing = self._extract_reprice_pricing(res_data)

            return {
                "success": True,
                "message": "PNR repriced successfully",
                "pricing": pricing,
                "raw_response": res_data,
            }
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"[Reprice] Sabre Error Response: {response.text}", flush=True)
            raise Exception(f"PNR reprice failed. {str(e)}{error_details}")

    def _extract_reprice_pricing(self, res_data: dict) -> dict:
        """
        Parses the AirPrice section of a CreatePassengerNameRecordRS response
        to extract fare totals for display to the user before confirming issuance.
        """
        pricing = {
            "total_fare": 0,
            "base_fare": 0,
            "tax_amount": 0,
            "currency": "BDT",
            "quote_number": 1,
        }

        try:
            rs = res_data.get("CreatePassengerNameRecordRS", {})

            # Extract quote number from AirPrice/PriceQuote section
            air_price_list = rs.get("AirPrice", [])
            if not isinstance(air_price_list, list):
                air_price_list = [air_price_list]

            for air_price in air_price_list:
                # Quote number
                pq_list = air_price.get("PriceQuote", [])
                if isinstance(pq_list, list) and pq_list:
                    pricing["quote_number"] = pq_list[0].get("RPH", 1)
                elif isinstance(pq_list, dict):
                    pricing["quote_number"] = pq_list.get("RPH", 1)

                # Fare amounts — try PricedItinerary > AirItineraryPricingInfo
                priced = air_price.get("PricedItinerary", [])
                if not isinstance(priced, list):
                    priced = [priced]

                for pit in priced:
                    pricing_info = pit.get("AirItineraryPricingInfo", {})
                    if not pricing_info:
                        continue

                    itin_total = pricing_info.get("ItinTotalFare", {})

                    # Total fare
                    total_fare_node = itin_total.get("TotalFare", {})
                    if total_fare_node:
                        pricing["total_fare"] = float(total_fare_node.get("Amount", 0) or 0)
                        pricing["currency"]   = total_fare_node.get("CurrencyCode", "BDT")

                    # Base fare
                    base_fare_node = itin_total.get("BaseFare", {})
                    if base_fare_node:
                        pricing["base_fare"] = float(base_fare_node.get("Amount", 0) or 0)

                    # Taxes
                    taxes_node = itin_total.get("Taxes", {})
                    if taxes_node:
                        pricing["tax_amount"] = float(taxes_node.get("TotalAmount", 0) or 0)

                    if pricing["total_fare"] > 0:
                        break

            # Fallback: derive tax from total - base
            if pricing["total_fare"] > 0 and pricing["tax_amount"] == 0 and pricing["base_fare"] > 0:
                pricing["tax_amount"] = round(pricing["total_fare"] - pricing["base_fare"], 2)

        except Exception as ex:
            print(f"[Reprice] Failed to parse pricing from response: {ex}", flush=True)

        return pricing

    def issue_ticket(self, ticketing_params: TicketingRequest) -> dict:
        """
        Issues an e-ticket for the given PNR.

        DesignatePrinter notes (Sabre REST AirTicketRQ v1.3.0):
          - Ticket.CountryCode : BSP/ARC country for settlement — do NOT add LNIATA here;
                                  it is invalid on the Ticket node and causes TKT PRT NOT ASSIGNED.
          - Hardcopy.LNIATA    : physical hardcopy printer address (optional, omitted when blank).
          - InvoiceItinerary.LNIATA: invoice printer address (optional, omitted when blank).

        ValidatingCarrier override:
          Pass `validating_carrier` in the request body to override the carrier on the stored
          Price Quote (PQ). Required when the PCC has ETA for a specific carrier but Sabre
          auto-assigned a different one during pricing (AUTH CARRIER INVLD-0633).
        """
        url = f"{self.base_url}{SabreEndpoints.ISSUE_TICKET}"
        headers = self.get_headers()

        lniata  = ticketing_params.printer_id or self.lniata
        country = ticketing_params.country_code or self.config.country_code or "BD"

        # ── Ticket printer: CountryCode only (no LNIATA — causes TKT PRT NOT ASSIGNED) ──
        printers: dict = {
            "Ticket": {
                "CountryCode": country
            }
        }
        # Only add physical printer nodes when an LNIATA is configured
        if lniata:
            printers["Hardcopy"]         = {"LNIATA": lniata}
            printers["InvoiceItinerary"] = {"LNIATA": lniata}

        # ── PricingQualifiers: quote record + optional validating carrier override ──────
        pricing_qualifiers: dict = {
            "PriceQuote": [
                {
                    "Record": [
                        {
                            "Number":  ticketing_params.quote_number or 1,
                            "Reissue": ticketing_params.reissue or False
                        }
                    ]
                }
            ]
        }
        # Note: In Sabre AirTicketRQ v1.3.0, ValidatingCarrier is NOT an allowed property under PricingQualifiers
        # (it must be specified during booking/pricing via FlightQualifiers in CreatePassengerNameRecordRQ).
        if ticketing_params.validating_carrier:
            vc_code = ticketing_params.validating_carrier.strip().upper()
            print(f"[Issue] Validating carrier specified: {vc_code} (handled via stored PriceQuote)", flush=True)


        payload = {
            "AirTicketRQ": {
                "version": "1.3.0",
                "DesignatePrinter": {
                    "Printers": printers
                },
                "Itinerary": {
                    "ID": ticketing_params.pnr
                },
                "Ticketing": [
                    {
                        "FOP_Qualifiers": {
                            "BasicFOP": {
                                "Type": ticketing_params.fop_type or "CA"
                            }
                        },
                        "MiscQualifiers": {
                            "Commission": {
                                "Percent": ticketing_params.commission_percent if ticketing_params.commission_percent is not None else 7
                            }
                        },
                        "PricingQualifiers": pricing_qualifiers
                    }
                ],
                "PostProcessing": {
                    "EndTransaction": {
                        "Source": {
                            "ReceivedFrom": f"{self.pcc} WEB"
                        }
                    }
                }
            }
        }

        print(f"[Issue] Sending Ticketing request to Sabre: {url} | PNR: {ticketing_params.pnr}", flush=True)
        print(f"[Issue] AirTicketRQ payload: {json.dumps(payload, indent=2)}", flush=True)

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"[Issue] Sabre Error Response: {response.text}", flush=True)
            raise Exception(f"Ticketing failed. {str(e)}{error_details}")

    def get_pnr_details(self, details_params: PNRDetailsRequest) -> dict:
        """
        Calls Sabre's Get Passenger Name Record API to retrieve full details of a booking.
        """
        url = f"{self.base_url}{SabreEndpoints.GET_PNR_DETAILS}"
        headers = self.get_headers()
        
        payload = {
            "confirmationId": details_params.pnr
        }
        
        print(f"Calling get_pnr_details for {details_params.pnr} at {url}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"PNR retrieval failed. {str(e)}{error_details}")

    def cancel_itinerary(self, cancel_params: CancelItineraryRequest) -> dict:
        """
        Calls Sabre's Cancel AtBooking API to cancel an existing PNR/itinerary.
        """
        url = f"{self.base_url}{SabreEndpoints.CANCEL_ITINERARY}"
        headers = self.get_headers()

        payload = {
            "confirmationId": cancel_params.pnr,
            "cancelAll": cancel_params.cancel_segments if cancel_params.cancel_segments is not None else True
        }

        print(f"Sending Cancel Itinerary request to Sabre: {url} | PNR: {cancel_params.pnr}")

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"Itinerary cancellation failed. {str(e)}{error_details}")

    def void_ticket(self, void_params: VoidTicketRequest) -> dict:
        """
        Calls Sabre's voidFlightTickets API to cancel an issued ticket (usually within 24 hours).
        """
        url = f"{self.base_url}{SabreEndpoints.VOID_TICKET}"
        headers = self.get_headers()
        
        payload = {
            "tickets": [void_params.ticket_number]
        }
        if void_params.pnr:
            payload["confirmationId"] = void_params.pnr
        
        print(f"Sending Void AtFlightTicket request to Sabre: {url} | AtFlightTicket: {void_params.ticket_number} | PNR: {void_params.pnr}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"AtFlightTicket voiding failed. {str(e)}{error_details}")

    def exchange_ticket(self, exchange_params: ExchangeTicketRequest) -> dict:
        """
        Calls Sabre's AirTicket API (/v1.3.0/air/ticket) with Reissue=True to process an automated ticket exchange.
        """
        url = f"{self.base_url}{SabreEndpoints.EXCHANGE_TICKET}"
        headers = self.get_headers()
        
        country = getattr(exchange_params, 'country_code', None) or self.config.country_code or "BD"
        lniata = self.lniata

        payload = {
            "AirTicketRQ": {
                "version": "1.3.0",
                "targetCity": self.pcc,
                "DesignatePrinter": {
                    "Printers": {
                        "Ticket": {
                            "CountryCode": country
                        },
                        "Hardcopy": {
                            "LNIATA": lniata
                        },
                        "InvoiceItinerary": {
                            "LNIATA": lniata
                        }
                    }
                },
                "Itinerary": {
                    "ID": exchange_params.pnr
                },
                "Ticketing": [
                    {
                        "FOP_Qualifiers": {
                            "BasicFOP": {
                                "Type": "CA"
                            }
                        },
                        "MiscQualifiers": {
                            "Commission": {
                                "Percent": 7
                            }
                        },
                        "PricingQualifiers": {
                            "PriceQuote": [
                                {
                                    "Record": [
                                        {
                                            "Number": 1,
                                            "Reissue": True
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ],
                "PostProcessing": {
                    "EndTransaction": {
                        "Source": {
                            "ReceivedFrom": f"{self.pcc} WEB"
                        }
                    }
                }
            }
        }
        
        print(f"[Exchange] Sending AtFlightTicket Exchange request to Sabre: {url} | PNR: {exchange_params.pnr} | Original AtFlightTicket: {exchange_params.original_ticket_number}", flush=True)
        
        try:
            response = self.session.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"[Exchange] Sabre Error Response: {response.text}", flush=True)
            raise Exception(f"AtFlightTicket exchange failed. {str(e)}{error_details}")

    def get_seat_maps(self, seat_params: SeatMapRequest) -> dict:
        """
        Calls Sabre's Seat Map API to retrieve available seats for a flight.
        """
        url = f"{self.base_url}{SabreEndpoints.SEAT_MAP}"
        headers = self.get_headers()
        
        p = _parse_sabre_segment(seat_params.flight_segment)
        payload = {
            "SeatMapRQ": {
                "version": "3.0.0",
                "Flight": {
                    "Destination": p["destination"],
                    "Origin": p["origin"],
                    "DepartureDate": p["departure_date"],
                    "MarketingAirline": p["marketing_airline"],
                    "FlightNumber": str(p["flight_number_int"] or p["flight_number_str"]),
                    "ResBookDesigCode": p["booking_class"]
                }
            }
        }

        if seat_params.pnr:
            payload["SeatMapRQ"]["BookingDetails"] = {"PNR": seat_params.pnr}
        
        print(f"Sending Seat Map request to Sabre: {url}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"Seat map retrieval failed. {str(e)}{error_details}")

    def get_baggage_allowance(self, baggage_params: BaggageAllowanceRequest) -> dict:
        """
        Calls Sabre's Baggage Allowance API.
        """
        url = f"{self.base_url}{SabreEndpoints.BAGGAGE_ALLOWANCE}"
        headers = self.get_headers()
        
        payload = {
            "BaggageAllowanceRQ": {
                 "version": "4.0.0",
                 "BookingDetails": {
                     "PNR": baggage_params.pnr
                 }
            }
        }
        
        print(f"Sending Baggage Allowance request to Sabre: {url} | PNR: {baggage_params.pnr}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"Baggage allowance retrieval failed. {str(e)}{error_details}")

    def place_in_queue(self, queue_params: QueueRequest) -> dict:
        """
        Calls Sabre's Queue Place API to manage agent queues.
        """
        url = f"{self.base_url}{SabreEndpoints.QUEUE_PLACE}"
        headers = self.get_headers()
        
        payload = {
            "QueuePlaceRQ": {
                "version": "1.0.0",
                "QueueInfo": {
                    "QueueIdentifier": [
                        {
                            "Number": queue_params.queue_number,
                            "PseudoCityCode": queue_params.pseudo_city_code
                        }
                    ],
                    "RecordLocator": queue_params.pnr
                }
            }
        }
        
        print(f"Sending Queue Place request to Sabre: {url} | PNR: {queue_params.pnr} -> Queue: {queue_params.queue_number}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"Queue placement failed. {str(e)}{error_details}")

    def get_fare_rules(self, rules_params: FareRulesRequest) -> dict:
        """
        Calls Sabre's Fare Rules API (/v1/offers/farerules).
        Retrieves structured fare rules for a given flight segment and fare basis.
        """
        url = f"{self.base_url}{SabreEndpoints.STRUCTURE_FARE_RULES}"
        headers = self.get_headers()

        p = _parse_sabre_segment(rules_params.flight_segment)

        # Build flight segment for fare rules lookup
        payload = {
            "originDestination": [
                {
                    "departure": {
                        "airportCode": p["origin"],
                        "date": p["departure_date"]
                    },
                    "arrival": {
                        "airportCode": p["destination"]
                    }
                }
            ],
            "travelers": [
                {
                    "passengerTypeCode": rules_params.flight_segment.get("passenger_type") or rules_params.flight_segment.get("passengerTypeCode") or "ADT"
                }
            ],
            "fareRulesRequest": {
                "fareBasisCode": rules_params.flight_segment.get("fare_basis_code") or rules_params.flight_segment.get("fareBasisCode"),
                "marketingAirlineCode": p["marketing_airline"],
                "flightNumber": str(p["flight_number_int"] or p["flight_number_str"]),
                "bookingClass": p["booking_class"],
                "departureDate": p["departure_date"],
                "origin": p["origin"],
                "destination": p["destination"]
            }
        }

        print(f"Sending Fare Rules request to Sabre: {url}")

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"Fare rules retrieval failed. {str(e)}{error_details}")
