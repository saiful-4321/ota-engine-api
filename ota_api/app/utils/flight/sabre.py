import datetime
import os
import json
from typing import Dict, Any, List

# Load airline names from data file
AIRLINE_NAMES = {}
try:
    # Path: app/utils/flight/../../data/airlines.json  → app/data/airlines.json
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_path = os.path.join(base_dir, "data", "airlines.json")
    if os.path.exists(data_path):
        with open(data_path, "r") as f:
            AIRLINE_NAMES = json.load(f)
            # print(f"DEBUG: Loaded {len(AIRLINE_NAMES)} airline names from {data_path}")
    else:
        print(f"WARNING: Airline data file not found at {data_path}")
except Exception as e:
    print(f"ERROR: Failed to load airlines.json: {e}")

def wrap_response(clean_data: Any, raw_data: Any, status: str = "success", message: str = "") -> Dict[str, Any]:
    """
    Wraps the response in a standard envelope that includes both 
    clean data and raw provider data.
    """
    return {
        "status": status,
        "message": message,
        "data": clean_data
    }

def _minutes_to_duration(minutes: int) -> str:
    """Convert elapsed minutes to 'Xh Ym' string."""
    if not minutes:
        return "N/A"
    h = minutes // 60
    m = minutes % 60
    return f"{h}h {m:02d}m"

def _build_filters(flights: list) -> Dict[str, Any]:
    """Build aggregated filter options from the formatted flights list."""
    airlines, stops_set, prices = set(), set(), []
    for f in flights:
        al = f.get("airline", {})
        if al.get("code"):
            # Use name if available, otherwise code
            name = al.get("name") or al.get("code")
            airlines.add((al["code"], name, al.get("logo", "")))
        
        # Count stops from the stops array
        stops_count = len(f.get("stops", []))
        stops_set.add(stops_count)
        
        if f.get("numericPrice"):
            prices.append(f["numericPrice"])

    # Format airlines for response
    formatted_airlines = []
    for code, name, logo in sorted(airlines, key=lambda x: x[1]):
        formatted_airlines.append({
            "code": code,
            "name": name,
            "logo": logo
        })

    return {
        "airlines": formatted_airlines,
        "stops": sorted(list(stops_set)),
        "priceRange": {
            "min": min(prices) if prices else 0,
            "max": max(prices) if prices else 0
        },
        "cabinClasses": ["Y", "S", "C", "J", "F"],
        "refundable": [True, False]
    }

def _get_airline_name(code: str, airline_descs: Dict[str, str], carrier_data: Dict[str, Any]) -> str:
    """Helper to get airline name from various sources with fallbacks."""
    if not code:
        return ""
    
    # Priority 1: From response's airlineDescs
    if code in airline_descs and airline_descs[code]:
        return airline_descs[code]
    
    # Priority 2: From carrier object directly
    if carrier_data.get("marketingAirlineName"):
        return carrier_data["marketingAirlineName"]
    
    # Priority 3: From local mapping
    if code in AIRLINE_NAMES:
        return AIRLINE_NAMES[code]
    
    # Priority 4: Fallback to code
    return code

def format_bfm_response(sabre_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses the Sabre Bargain Finder Max (BFM) response and formats it
    into the flightData.json-compatible structure expected by the OTA frontend.
    """
    if "groupedItineraryResponse" not in sabre_response:
        return sabre_response

    try:
        grouped = sabre_response["groupedItineraryResponse"]
        leg_descs      = {l["id"]: l for l in grouped.get("legDescs", [])}
        schedule_descs = {s["id"]: s for s in grouped.get("scheduleDescs", [])}
        
        # Extract airline names from airlineDescs if present
        airline_descs = {}
        for airline in grouped.get("airlineDescs", []):
            airline_descs[airline["code"]] = airline.get("name", "")

        formatted_flights = []

        for group in grouped.get("itineraryGroups", []):
            group_key = group.get("groupDescription", {}).get("legDescriptions", [{}])[0]
            dep_date_str = group_key.get("departureDate", "")

            for itin in group.get("itineraries", []):
                # ── Pricing ──────────────────────────────────────────────
                pricing_info = itin.get("pricingInformation", [])
                total_price_num = 0
                total_price_str = "$0"
                base_fare       = 0
                taxes           = 0
                currency        = "BDT"
                validating_carrier = ""
                is_refundable   = True
                baggage_summary = None
                seats_remaining = None
                fare_components = []
                baggage_info    = []

                if pricing_info:
                    fare       = pricing_info[0].get("fare", {})
                    total_fare = fare.get("totalFare", {})
                    total_price_num = total_fare.get("totalPrice", 0) or 0
                    base_fare       = fare.get("baseFareAmount", 0) or 0
                    taxes           = fare.get("totalTaxAmount", 0) or 0
                    currency        = total_fare.get("currency", "BDT")
                    validating_carrier = fare.get("validatingCarrierCode", "")

                    total_price_str = f"${total_price_num:,.0f}" if currency == "USD" else f"{total_price_num:,.0f} {currency}"

                    pax_list = fare.get("passengerInfoList", [])
                    if pax_list:
                        p_info         = pax_list[0].get("passengerInfo", {})
                        is_refundable  = not p_info.get("nonRefundable", False)
                        fare_components = p_info.get("fareComponents", [])
                        baggage_info    = p_info.get("baggageInformation", [])

                segment_details: Dict[int, Dict] = {}
                for fc in fare_components:
                    for seg in fc.get("segments", []):
                        s = seg.get("segment", {})
                        sid = s.get("id")
                        if sid is not None:
                            segment_details[sid] = {
                                "cabin_code":      s.get("cabinCode"),
                                "seats_remaining": s.get("seatsAvailable"),
                                "booking_code":    s.get("resBookDesigCode"),
                            }
                            if seats_remaining is None:
                                seats_remaining = s.get("seatsAvailable")

                if baggage_info:
                    allowance = baggage_info[0].get("allowance", {})
                    pieces = allowance.get("pieces")
                    weight = allowance.get("weight")
                    unit   = allowance.get("unit", "kg")
                    if pieces is not None:
                        baggage_summary = f"{pieces}PC"
                    elif weight is not None:
                        baggage_summary = f"{weight}{unit.upper()}"

                # ── Legs ─────────────────────────────────────────────────
                legs_out   = []
                all_stops  = []
                first_dep  = {}
                last_arr   = {}
                top_airline_code = validating_carrier
                top_airline_name = _get_airline_name(top_airline_code, airline_descs, {})
                top_airline_logo = f"https://images.daisycon.io/airline/{top_airline_code}.png" if top_airline_code else ""

                for leg_idx, itin_leg in enumerate(itin.get("legs", [])):
                    leg_ref     = itin_leg.get("ref", 0)
                    leg_details = leg_descs.get(leg_ref, {})
                    schedules   = leg_details.get("schedules", [])

                    elapsed = leg_details.get("elapsedTime")
                    duration_str = _minutes_to_duration(elapsed)

                    leg_stops    = []
                    leg_segments = []
                    leg_layovers = []
                    first_dep_date_in_leg = None

                    for idx, sched in enumerate(schedules):
                        sched_ref     = sched.get("ref", 0)
                        sched_details = schedule_descs.get(sched_ref, {})
                        departure     = sched_details.get("departure", {})
                        arrival       = sched_details.get("arrival", {})
                        carrier       = sched_details.get("carrier", {})
                        seg_info      = segment_details.get(sched_ref, {})

                        if idx == 0:
                            first_dep_date_in_leg = departure.get("date")
                            if leg_idx == 0:
                                first_dep = {
                                    "time":     departure.get("time", "")[:5],
                                    "code":     departure.get("airport", ""),
                                    "city":     departure.get("city", ""),
                                    "airport":  departure.get("airportName", departure.get("airport", "")),
                                    "terminal": departure.get("terminal")
                                }
                                mktg = carrier.get("marketing", "")
                                top_airline_code = mktg or validating_carrier
                                top_airline_name = _get_airline_name(top_airline_code, airline_descs, carrier)
                                top_airline_logo = f"https://images.daisycon.io/airline/{top_airline_code}.png"

                        if idx > 0:
                            stop_code = departure.get("airport", "")
                            if stop_code:
                                leg_stops.append(stop_code)
                                all_stops.append(stop_code)

                        day_offset = 0
                        if first_dep_date_in_leg and arrival.get("date"):
                            try:
                                d1 = datetime.datetime.strptime(first_dep_date_in_leg, "%Y-%m-%d").date()
                                d2 = datetime.datetime.strptime(arrival["date"], "%Y-%m-%d").date()
                                day_offset = (d2 - d1).days
                            except Exception:
                                pass

                        mktg_code = carrier.get("marketing", "")
                        mktg_name = _get_airline_name(mktg_code, airline_descs, carrier)
                        aircraft  = carrier.get("equipment", {}).get("code", "")

                        segment = {
                            "flightNumber": str(carrier.get("marketingFlightNumber", "")),
                            "airline": {
                                "code":     mktg_code,
                                "name":     mktg_name,
                                "aircraft": aircraft,
                                "logo":     f"https://images.daisycon.io/airline/{mktg_code}.png"
                            },
                            "departure": {
                                "time":     departure.get("time", "")[:5],
                                "code":     departure.get("airport", ""),
                                "city":     departure.get("city", ""),
                                "airport":  departure.get("airportName", departure.get("airport", "")),
                                "terminal": departure.get("terminal")
                            },
                            "arrival": {
                                "time":          arrival.get("time", "")[:5],
                                "code":          arrival.get("airport", ""),
                                "city":          arrival.get("city", ""),
                                "airport":       arrival.get("airportName", arrival.get("airport", "")),
                                "terminal":      arrival.get("terminal"),
                                "dayOffset":     day_offset if day_offset else None
                            },
                            "duration":        _minutes_to_duration(sched_details.get("elapsedTime")),
                            "stops":           [],
                            "baggage":         baggage_summary or "23kg",
                            "cabinClass":      seg_info.get("cabin_code"),
                            "bookingCode":     seg_info.get("booking_code"),
                            "seatsRemaining":  seg_info.get("seats_remaining"),
                            "amenities": {
                                "wifi":          False,
                                "meal":          True,
                                "entertainment": True,
                                "power":         True
                            }
                        }
                        leg_segments.append(segment)

                        if idx < len(schedules) - 1:
                            next_ref     = schedules[idx + 1].get("ref", 0)
                            next_details = schedule_descs.get(next_ref, {})
                            next_dep     = next_details.get("departure", {})
                            layover_str  = None
                            layover_mins = 0
                            try:
                                arr_dt = datetime.datetime.strptime(
                                    f"{arrival.get('date')} {arrival.get('time','')[:5]}", "%Y-%m-%d %H:%M")
                                dep_dt = datetime.datetime.strptime(
                                    f"{next_dep.get('date')} {next_dep.get('time','')[:5]}", "%Y-%m-%d %H:%M")
                                layover_mins = int((dep_dt - arr_dt).total_seconds() / 60)
                                layover_str  = _minutes_to_duration(layover_mins)
                            except Exception:
                                pass
                            leg_layovers.append({
                                "airport":          arrival.get("airport"),
                                "terminal":         arrival.get("terminal"),
                                "duration":         layover_str,
                                "duration_minutes": layover_mins
                            })

                        if leg_idx == 0:
                            last_arr = {
                                "time":     arrival.get("time", "")[:5],
                                "code":     arrival.get("airport", ""),
                                "city":     arrival.get("city", ""),
                                "airport":  arrival.get("airportName", arrival.get("airport", "")),
                                "terminal": arrival.get("terminal")
                            }

                    legs_out.append({
                        "flightNumber": leg_segments[0]["flightNumber"] if leg_segments else "",
                        "airline":      leg_segments[0]["airline"]      if leg_segments else {},
                        "departure":    leg_segments[0]["departure"]    if leg_segments else {},
                        "arrival":      leg_segments[-1]["arrival"]     if leg_segments else {},
                        "duration":     duration_str,
                        "stops":        leg_stops,
                        "baggage":      baggage_summary or "23kg",
                        "amenities": {
                            "wifi":          False,
                            "meal":          True,
                            "entertainment": True,
                            "power":         True
                        },
                        "segments":  leg_segments,
                        "layovers":  leg_layovers
                    })

                journey_date = ""
                if dep_date_str:
                    try:
                        journey_date = datetime.datetime.strptime(dep_date_str, "%Y-%m-%d").strftime("%b %d, %Y")
                    except Exception:
                        journey_date = dep_date_str

                num_legs = len(legs_out)
                if num_legs == 1:
                    trip_type = "one-way"
                elif num_legs == 2:
                    trip_type = "round-trip"
                else:
                    trip_type = "multi-city"

                formatted_flight = {
                    "id":             str(itin.get("id", "")),
                    "tripType":       trip_type,
                    "airline": {
                        "code": top_airline_code,
                        "name": top_airline_name,
                        "logo": top_airline_logo
                    },
                    "departure":      first_dep,
                    "arrival":        last_arr,
                    "duration":       legs_out[0]["duration"] if legs_out else "N/A",
                    "price":          total_price_str,
                    "numericPrice":   total_price_num,
                    "baseFare":       base_fare,
                    "taxes":          taxes,
                    "currency":       currency,
                    "stops":          all_stops,
                    "journeyDate":    journey_date,
                    "isRefundable":   is_refundable,
                    "baggageSummary": baggage_summary,
                    "seatsRemaining": seats_remaining,
                    "validatingCarrier": validating_carrier,
                    "legs":           legs_out
                }
                formatted_flights.append(formatted_flight)

        filters = _build_filters(formatted_flights)

        return {
            "status": "success",
            "metadata": {
                "total_results": len(formatted_flights)
            },
            "filters": filters,
            "flights": formatted_flights,
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error parsing BFM response: {e}")
        return sabre_response

def format_pnr_response(sabre_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the Sabre CreatePassengerNameRecordRS response into a 
    clean, exhaustive structure for the frontend, avoiding duplication.
    """
    if "CreatePassengerNameRecordRS" not in sabre_response:
        return {
            "status": "error",
            "message": "Invalid response from Sabre",
            "details": sabre_response
        }

    rs = sabre_response["CreatePassengerNameRecordRS"]
    results = rs.get("ApplicationResults", {})
    status = results.get("status")
    
    # Extract PNR (Record Locator)
    pnr = rs.get("ItineraryRef", {}).get("ID", "N/A")
    
    if status == "Complete":
        # Extract segments for summary
        segments = []
        air_book = rs.get("AirBook", {})
        option = air_book.get("OriginDestinationOption", {})
        seg_list = option.get("FlightSegment", [])
        
        for seg in seg_list:
            segments.append({
                "flightNumber": seg.get("FlightNumber"),
                "numberInParty": seg.get("NumberInParty"),
                "airline": {
                    "marketing": seg.get("MarketingAirline", {}).get("Code"),
                    "marketingFlightNumber": seg.get("MarketingAirline", {}).get("FlightNumber")
                },
                "origin": {
                    "code": seg.get("OriginLocation", {}).get("LocationCode")
                },
                "destination": {
                    "code": seg.get("DestinationLocation", {}).get("LocationCode")
                },
                "departure": seg.get("DepartureDateTime"),
                "arrival": seg.get("ArrivalDateTime"),
                "status": seg.get("Status"),
                "bookingClass": seg.get("ResBookDesigCode"),
                "eTicket": seg.get("eTicket")
            })

        return {
            "status": "success",
            "pnr": pnr,
            "booking": {
                "pnr": pnr,
                "status": "Confirmed",
                "creation_time": results.get("Success", [{}])[0].get("timeStamp"),
                "itinerary": segments,
                "applicationResults": results,
                "links": sabre_response.get("Links", [])
            },
        }
    else:
        # Handle errors
        errors = results.get("Error", [])
        error_msg = "Booking failed"
        if errors:
            msg_list = errors[0].get("SystemSpecificResults", [{}])[0].get("Message", [])
            if msg_list:
                error_msg = msg_list[0].get("value") or str(msg_list[0])

        return {
            "status": "error",
            "pnr": None,
            "message": error_msg,
            "errors": errors,
            "links": sabre_response.get("Links", [])
        }

def format_pnr_details_response(sabre_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the Sabre getBooking response into a clean, exhaustive 
    detailed structure for the frontend, avoiding duplication.
    """
    data = sabre_response.get("trip", sabre_response)
    
    pnr = data.get("bookingId") or data.get("confirmationId")
    if not pnr:
        errors = data.get("errors", [])
        return {
            "status": "error",
            "message": errors[0].get("description", "PNR not found or invalid response") if errors else "Invalid response",
            "errors": errors
        }

    # 1. Flights / Itinerary
    itinerary = []
    for flight in data.get("flights", []):
        itinerary.append({
            "id": flight.get("itemId"),
            "confirmationId": flight.get("confirmationId"),
            "flightNumber": str(flight.get("flightNumber")),
            "airline": {
                "code": flight.get("airlineCode"),
                "name": flight.get("airlineName"),
                "logo": f"https://images.daisycon.io/airline/{flight.get('airlineCode')}.png"
            },
            "operatingAirline": {
                "code": flight.get("operatingAirlineCode"),
                "name": flight.get("operatingAirlineName"),
                "flightNumber": str(flight.get("operatingFlightNumber"))
            },
            "departure": {
                "code": flight.get("fromAirportCode"),
                "date": flight.get("departureDate"),
                "time": flight.get("departureTime"),
                "terminal": flight.get("departureTerminalName"),
                "gate": flight.get("departureGate")
            },
            "arrival": {
                "code": flight.get("toAirportCode"),
                "date": flight.get("arrivalDate"),
                "time": flight.get("arrivalTime"),
                "terminal": flight.get("arrivalTerminalName")
            },
            "status": {
                "code": flight.get("flightStatusCode"),
                "name": flight.get("flightStatusName")
            },
            "details": {
                "cabin": flight.get("cabinTypeName"),
                "bookingClass": flight.get("bookingClass"),
                "aircraft": flight.get("aircraftTypeName"),
                "durationMinutes": flight.get("durationInMinutes"),
                "distanceMiles": flight.get("distanceInMiles"),
                "seats": flight.get("numberOfSeats")
            },
            "meals": flight.get("meals", [])
        })

    # 2. Passengers / Travelers
    passengers = []
    for traveler in data.get("travelers", []):
        passengers.append({
            "id": traveler.get("nameAssociationId"),
            "firstName": traveler.get("givenName"),
            "lastName": traveler.get("surname"),
            "type": traveler.get("passengerCode") or traveler.get("type"),
            "index": traveler.get("travelerIndex")
        })

    # 3. Special Services (SSRs)
    special_services = []
    for ss in data.get("specialServices", []):
        special_services.append({
            "code": ss.get("code"),
            "message": ss.get("message")
        })

    # 4. Journeys Summary
    journeys = data.get("journeys", [])

    # 5. Creation & Metadata
    creation = data.get("creationDetails", {})

    return {
        "status": "success",
        "pnr": pnr,
        "booking": {
            "pnr": pnr,
            "ticketingStatus": "Ticketed" if data.get("isTicketed") else "Pending",
            "isCancelable": data.get("isCancelable", True),
            "creation": {
                "user": creation.get("creationUserSine"),
                "date": creation.get("creationDate"),
                "time": creation.get("creationTime"),
                "pcc": creation.get("userWorkPcc")
            },
            "contact": data.get("contactInfo", {}),
            "itinerary": itinerary,
            "passengers": passengers,
            "journeys": journeys,
            "specialServices": special_services,
            "warnings": data.get("errors", []), # Sabre often puts warnings in 'errors' list
            "signature": data.get("bookingSignature"),
            "timestamp": data.get("timestamp")
        },
    }
def format_ticketing_response(sabre_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the Sabre AirTicketRS response into a clean, user-friendly structure.
    """
    air_ticket_rs = sabre_response.get("AirTicketRS", {})
    app_results = air_ticket_rs.get("ApplicationResults", {})
    rs_status = app_results.get("status")
    
    # Success if status is 'Complete'
    is_success = rs_status == "Complete" or sabre_response.get("status") == "Success"
    
    message = "Tickets issued successfully"
    error_details = []

    if not is_success:
        message = "Ticketing failed"
        
        # 1. Try to find a specific cause in Warnings (Sabre often puts the real reason there)
        warnings = app_results.get("Warning", [])
        for warn in warnings:
            for sys_res in warn.get("SystemSpecificResults", []):
                for msg in sys_res.get("Message", []):
                    content = msg.get("content") or msg.get("value")
                    if content:
                        error_details.append(content)

        # 2. Extract main Errors
        errors = app_results.get("Error", [])
        for err in errors:
            for sys_res in err.get("SystemSpecificResults", []):
                for msg in sys_res.get("Message", []):
                    content = msg.get("content") or msg.get("value")
                    if content and content not in error_details:
                        error_details.append(content)

        # 3. Formulate a better message
        if error_details:
            # If the first error is generic, use the more specific one
            if "No new tickets have been issued" in error_details[0] and len(error_details) > 1:
                message = error_details[1]
            else:
                message = error_details[0]

    return {
        "status": "success" if is_success else "error",
        "message": message,
        "ticketing": {
            "status": rs_status or sabre_response.get("status"),
            "pnr": air_ticket_rs.get("Itinerary", {}).get("ID"),
            "errors": error_details,
            "timestamp": app_results.get("Error", [{}])[0].get("timeStamp") if error_details else None
        },
    }

def format_pricing_response(sabre_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the Sabre flightCheck response into a premium, standardized structure.
    Resolves flight references and extracts detailed fare information.
    """
    if "errors" in sabre_response:
        return {
            "status": "error",
            "message": sabre_response["errors"][0].get("description", "Pricing revalidation failed"),
            "details": sabre_response["errors"],
        }

    # 1. Map flights by ID for easy lookup
    flights_map = {f["id"]: f for f in sabre_response.get("flights", [])}
    
    # 2. Extract Offer details (Take the first/main offer)
    offers = sabre_response.get("offers", [])
    formatted_offers = []
    
    for offer in offers:
        total_price = offer.get("totalPrice", {})
        
        # Get fare breakdown from the first item/fare
        fare_details = {}
        items = offer.get("items", [])
        if items:
            fares = items[0].get("fares", [])
            if fares:
                fare_total = fares[0].get("fareTotal", {})
                fare_details = {
                    "baseFare": fare_total.get("equivalentFare"),
                    "taxAmount": fare_total.get("taxAmount"),
                    "totalAmount": fare_total.get("amount"),
                    "currency": fare_total.get("currencyCode")
                }
        
        # Resolve itinerary for this offer
        offer_itinerary = []
        journey_refs = offer.get("journeyRefs", [])
        for j_ref in journey_refs:
            # Find the journey in sabre_response
            journey = next((j for j in sabre_response.get("journeys", []) if j["id"] == j_ref), None)
            if journey:
                for f_ref in journey.get("flightRefs", []):
                    flight = flights_map.get(f_ref)
                    if flight:
                        offer_itinerary.append({
                            "flightNumber": flight.get("marketingFlightNumber"),
                            "airline": {
                                "marketing": flight.get("marketingAirlineCode"),
                                "operating": flight.get("operatingAirlineCode")
                            },
                            "origin": flight.get("departureAirportCode"),
                            "destination": flight.get("arrivalAirportCode"),
                            "departure": f"{flight.get('departureDate')} {flight.get('departureTime')}",
                            "arrival": f"{flight.get('arrivalDate')} {flight.get('arrivalTime')}",
                            "durationMinutes": flight.get("durationInMinutes"),
                            "aircraft": flight.get("aircraftTypeCode")
                        })
        
        formatted_offers.append({
            "offerId": offer.get("id"),
            "price": fare_details,
            "itinerary": offer_itinerary,
            "validUntil": offer.get("validUntil")
        })

    # For the main response, we use the first offer as the 'recommended' one
    main_offer = formatted_offers[0] if formatted_offers else {}

    return {
        "status": "success",
        "message": "Flight price revalidated successfully",
        "pricing": {
            "total": main_offer.get("price", {}).get("totalAmount"),
            "base": main_offer.get("price", {}).get("baseFare"),
            "taxes": main_offer.get("price", {}).get("taxAmount"),
            "currency": main_offer.get("price", {}).get("currency"),
            "itinerary": main_offer.get("itinerary", []),
            "allOffers": formatted_offers # Include alternatives if any
        },
    }

def format_cancel_response(sabre_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the Sabre cancelBooking response into a clean, standardized structure.
    """
    # Sabre cancelBooking returns an errors array on failure
    errors = sabre_response.get("errors", [])
    if errors:
        first_error = errors[0]
        return {
            "status": "error",
            "message": first_error.get("description") or first_error.get("message", "Cancellation failed"),
            "errors": errors,
        }

    # On success, Sabre echoes the request back — the PNR is inside request.confirmationId
    request_echo = sabre_response.get("request", {})
    confirmation_id = (
        sabre_response.get("confirmationId")             # top-level (some versions)
        or request_echo.get("confirmationId")            # echoed request (v1 cancelBooking)
    )

    cancelled_flights = []
    for flight in sabre_response.get("flights", []):
        cancelled_flights.append({
            "flightNumber": flight.get("flightNumber"),
            "airline": flight.get("airlineCode"),
            "origin": flight.get("fromAirportCode"),
            "destination": flight.get("toAirportCode"),
            "departure": f"{flight.get('departureDate', '')} {flight.get('departureTime', '')}".strip(),
            "status": flight.get("status")
        })

    return {
        "status": "success",
        "message": f"Itinerary {confirmation_id} has been successfully cancelled.",
        "cancellation": {
            "pnr": confirmation_id,
            "cancelledAt": sabre_response.get("timestamp"),
            "cancelledAll": request_echo.get("cancelAll", True),
            "cancelledSegments": cancelled_flights,
        },
    }

def format_fare_rules_response(sabre_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats Sabre's /v1/offers/farerules response into a clean, structured format.
    """
    # Handle errors
    errors = sabre_response.get("errors", [])
    if errors:
        first_error = errors[0]
        return {
            "status": "error",
            "message": first_error.get("description") or first_error.get("message", "Fare rules retrieval failed"),
            "errors": errors
        }

    # Extract fare rules categories
    formatted_rules = []
    for rule in sabre_response.get("fareRules", []):
        categories = []
        for cat in rule.get("ruleCategories", []):
            categories.append({
                "categoryNumber": cat.get("categoryNumber"),
                "categoryName": cat.get("categoryName"),
                "text": cat.get("rules", [{}])[0].get("text") if cat.get("rules") else None
            })

        formatted_rules.append({
            "fareBasisCode": rule.get("fareBasisCode"),
            "airline": rule.get("validatingAirlineCode"),
            "origin": rule.get("origin"),
            "destination": rule.get("destination"),
            "passengerType": rule.get("passengerTypeCode"),
            "categories": categories
        })

    return {
        "status": "success",
        "message": "Fare rules retrieved successfully",
        "fareRules": formatted_rules
    }

def format_error_response(error: Exception) -> Dict[str, Any]:
    """
    Standardizes exception messages into a consistent JSON error structure.
    Parses 'Details:' if present in the exception string to extract raw Sabre JSON.
    """
    error_str = str(error)
    message = error_str
    details = None

    # Try to extract JSON details if present (service methods append " | Details: {json}")
    if " | Details: " in error_str:
        parts = error_str.split(" | Details: ")
        message = parts[0]
        try:
            details = json.loads(parts[1])
            # If details has a more specific message, promote it
            if isinstance(details, dict):
                if "message" in details:
                    message = f"{message}: {details['message']}"
                elif "description" in details:
                    message = f"{message}: {details['description']}"
        except:
            details = parts[1]

    return {
        "status": "error",
        "message": message,
        "details": details,
        "timestamp": datetime.datetime.now().isoformat()
    }

