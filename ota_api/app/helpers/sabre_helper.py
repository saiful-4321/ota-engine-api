import datetime
import os
import json
from typing import Dict, Any, List

# Load airline names from data file
AIRLINE_NAMES = {}
try:
    # Path: app/helpers/../data/airlines.json
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_dir, "data", "airlines.json")
    if os.path.exists(data_path):
        with open(data_path, "r") as f:
            AIRLINE_NAMES = json.load(f)
            # print(f"DEBUG: Loaded {len(AIRLINE_NAMES)} airline names from {data_path}")
    else:
        print(f"WARNING: Airline data file not found at {data_path}")
except Exception as e:
    print(f"ERROR: Failed to load airlines.json: {e}")

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
                currency        = "USD"
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
                    currency        = total_fare.get("currency", "USD")
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
            "flights": formatted_flights
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error parsing BFM response: {e}")
        return sabre_response
