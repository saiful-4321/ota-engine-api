import re
import datetime
from typing import Dict, Any
from app.utils.flight.sabre import _build_filters, AIRLINE_NAMES


def _parse_iso_duration(duration_str: str) -> tuple:
    """Parses ISO 8601 duration e.g. PT4H50M, PT6H, PT35M into (total_minutes, '4h 50m')."""
    if not duration_str:
        return 0, "N/A"
    hours = 0
    minutes = 0
    m_h = re.search(r'(\d+)H', duration_str)
    if m_h:
        hours = int(m_h.group(1))
    m_m = re.search(r'(\d+)M', duration_str)
    if m_m:
        minutes = int(m_m.group(1))
    total_mins = hours * 60 + minutes
    if hours > 0 and minutes > 0:
        fmt = f"{hours}h {minutes:02d}m"
    elif hours > 0:
        fmt = f"{hours}h"
    else:
        fmt = f"{minutes}m"
    return total_mins, fmt


def _format_time(time_str: str) -> str:
    """Extracts HH:MM from HH:MM:SS or ISO string."""
    if not time_str:
        return ""
    parts = time_str.split(":")
    return f"{parts[0]}:{parts[1]}" if len(parts) >= 2 else time_str


def format_catalog_search_response(travelport_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses Travelport JSON API v11 CatalogProductOfferingsResponse
    into the unified flightData schema expected by the OTA frontend.
    """
    if not isinstance(travelport_response, dict):
        return travelport_response

    root = travelport_response.get("CatalogProductOfferingsResponse", {})
    if not root:
        return travelport_response

    offerings = root.get("CatalogProductOfferings", {}).get("CatalogProductOffering", [])
    if not offerings:
        err_msg = "No flights found for the requested route and date."
        errors = root.get("Result", {}).get("Error", [])
        if errors and isinstance(errors, list):
            err_msg = errors[0].get("Message", err_msg)

        return {
            "status": "no_results",
            "message": err_msg,
            "metadata": {
                "total_results": 0,
                "errors": errors
            },
            "filters": {},
            "flights": []
        }

    # Reference lookup maps
    flights_dict = {}
    products_dict = {}
    brands_dict = {}
    terms_dict = {}

    for ref in root.get("ReferenceList", []):
        rtype = ref.get("@type")
        if rtype == "ReferenceListFlight":
            for f in ref.get("Flight", []):
                flights_dict[f.get("id")] = f
        elif rtype == "ReferenceListProduct":
            for p in ref.get("Product", []):
                products_dict[p.get("id")] = p
        elif rtype == "ReferenceListBrand":
            for b in ref.get("Brand", []):
                brands_dict[b.get("id")] = b
        elif rtype == "ReferenceListTermsAndConditions":
            for t in ref.get("TermsAndConditions", []):
                terms_dict[t.get("id")] = t

    formatted_flights = []

    trace_id = travelport_response.get("_trace_id", "")
    root = travelport_response.get("CatalogProductOfferingsResponse", {})
    transaction_id = root.get("transactionId", "")
    cpo_id = root.get("CatalogProductOfferings", {}).get("Identifier", {}).get("value") or transaction_id

    for idx, off in enumerate(offerings):
        raw_offer_id = off.get("id", f"cpo_{idx}")
        options = off.get("ProductBrandOptions", [])

        for opt in options:
            f_refs = opt.get("flightRefs", [])
            flight_objs = [flights_dict[r] for r in f_refs if r in flights_dict]
            if not flight_objs:
                continue

            for pbo in opt.get("ProductBrandOffering", []):
                # Extract productRef for this specific flight offering option
                prod_ref = "p0"
                prods = pbo.get("Product", [])
                if prods and isinstance(prods, list) and isinstance(prods[0], dict):
                    prod_ref = prods[0].get("productRef") or "p0"

                top_c = flight_objs[0].get("carrier", "")
                if trace_id and cpo_id:
                    offer_id = f"{raw_offer_id}@@{trace_id}@@{cpo_id}@@{prod_ref}@@{top_c}"
                elif trace_id:
                    offer_id = f"{raw_offer_id}@@{trace_id}@@@@{prod_ref}@@{top_c}"
                else:
                    offer_id = raw_offer_id
                price_detail = pbo.get("BestCombinablePrice", {})
                total_price_num = price_detail.get("TotalPrice", 0)
                base_fare = price_detail.get("Base", 0)
                taxes = price_detail.get("TotalTaxes", 0)
                currency = price_detail.get("CurrencyCode", {}).get("value", "BDT")
                total_price_str = f"{currency} {total_price_num:,}"

                # Baggage
                baggage_summary = "20kg"

                # Build segments
                leg_segments = []
                leg_layovers = []
                total_journey_mins = 0

                for s_idx, f_obj in enumerate(flight_objs):
                    dep_info = f_obj.get("Departure", {})
                    arr_info = f_obj.get("Arrival", {})
                    carrier_code = f_obj.get("carrier", "")
                    airline_name = AIRLINE_NAMES.get(carrier_code, carrier_code)
                    flight_num = f_obj.get("number", "")
                    seg_dur_mins, seg_dur_str = _parse_iso_duration(f_obj.get("duration", ""))
                    total_journey_mins += seg_dur_mins

                    seg_dict = {
                        "flightNumber": flight_num,
                        "airline": {
                            "code": carrier_code,
                            "name": airline_name,
                            "logo": f"https://pics.avs.io/al_sha/100/100/{carrier_code}.png" if carrier_code else ""
                        },
                        "operatingAirline": {
                            "code": carrier_code,
                            "name": airline_name,
                            "flightNumber": flight_num
                        },
                        "departure": {
                            "date": dep_info.get("date", ""),
                            "time": _format_time(dep_info.get("time", "")),
                            "code": dep_info.get("location", ""),
                            "city": "",
                            "airport": dep_info.get("location", ""),
                            "terminal": dep_info.get("terminal", "")
                        },
                        "arrival": {
                            "date": arr_info.get("date", ""),
                            "time": _format_time(arr_info.get("time", "")),
                            "code": arr_info.get("location", ""),
                            "city": "",
                            "airport": arr_info.get("location", ""),
                            "terminal": arr_info.get("terminal", "")
                        },
                        "duration": seg_dur_str,
                        "durationMinutes": seg_dur_mins,
                        "cabin": "Economy",
                        "bookingClass": "Y",
                        "aircraft": f_obj.get("equipment", ""),
                        "layover": None
                    }

                    # Layover calculation between segments
                    if s_idx < len(flight_objs) - 1:
                        next_f = flight_objs[s_idx + 1]
                        next_dep = next_f.get("Departure", {})
                        try:
                            arr_dt = datetime.datetime.strptime(
                                f"{arr_info.get('date')} {dep_info.get('time')[:5]}", "%Y-%m-%d %H:%M"
                            )
                            next_dep_dt = datetime.datetime.strptime(
                                f"{next_dep.get('date')} {next_dep.get('time')[:5]}", "%Y-%m-%d %H:%M"
                            )
                            layover_mins = max(0, int((next_dep_dt - arr_dt).total_seconds() / 60))
                            h = layover_mins // 60
                            m = layover_mins % 60
                            layover_str = f"{h}h {m:02d}m" if h > 0 else f"{m}m"
                        except Exception:
                            layover_mins = 0
                            layover_str = "Connection"

                        seg_dict["layover"] = layover_str
                        leg_layovers.append({
                            "airport": arr_info.get("location", ""),
                            "terminal": arr_info.get("terminal", ""),
                            "duration": layover_str,
                            "duration_minutes": layover_mins
                        })

                    leg_segments.append(seg_dict)

                if not leg_segments:
                    continue

                top_carrier = leg_segments[0]["airline"]["code"]
                top_airline_name = leg_segments[0]["airline"]["name"]
                first_dep = leg_segments[0]["departure"]
                last_arr = leg_segments[-1]["arrival"]
                stops_list = [seg["arrival"]["code"] for seg in leg_segments[:-1]]

                h_total = total_journey_mins // 60
                m_total = total_journey_mins % 60
                overall_duration_str = f"{h_total}h {m_total:02d}m" if h_total > 0 else f"{m_total}m"

                leg = {
                    "flightNumber": leg_segments[0]["flightNumber"],
                    "airline": leg_segments[0]["airline"],
                    "departure": first_dep,
                    "arrival": last_arr,
                    "duration": overall_duration_str,
                    "stops": stops_list,
                    "baggage": baggage_summary,
                    "amenities": {
                        "wifi": False,
                        "meal": True,
                        "entertainment": True,
                        "power": True
                    },
                    "segments": leg_segments,
                    "layovers": leg_layovers
                }

                pbo_content_src = str(pbo.get("ContentSource") or off.get("ContentSource") or "").upper()
                is_ndc = ("NDC" in pbo_content_src)

                formatted_flight = {
                    "id": offer_id,
                    "tripType": "one-way",
                    "airline": {
                        "code": top_carrier,
                        "name": top_airline_name,
                        "logo": f"https://pics.avs.io/al_sha/100/100/{top_carrier}.png" if top_carrier else ""
                    },
                    "departure": first_dep,
                    "arrival": last_arr,
                    "duration": overall_duration_str,
                    "price": total_price_str,
                    "numericPrice": total_price_num,
                    "baseFare": base_fare,
                    "taxes": taxes,
                    "currency": currency,
                    "stops": stops_list,
                    "journeyDate": first_dep.get("date", ""),
                    "isRefundable": True,
                    "baggageSummary": baggage_summary,
                    "seatsRemaining": 9,
                    "validatingCarrier": top_carrier,
                    "apiProvider": "Travelport",
                    "api_provider": "travelport",
                    "pcc": "3Q3I",
                    "isNdc": is_ndc,
                    "is_ndc": is_ndc,
                    "fareType": "NDC" if is_ndc else "GDS",
                    "fare_type": "NDC" if is_ndc else "GDS",
                    "tags": ["NDC"] if is_ndc else [],
                    "contentSource": "NDC" if is_ndc else "GDS",
                    "legs": [leg]
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

def format_pnr_response(travelport_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the Travelport reservation commit response into a standardized structure
    containing the PNR (locator), travelers, status, and itinerary.
    """
    if "ReservationResponse" not in travelport_response:
        return {
            "status": "error",
            "message": "Invalid response from Travelport",
            "details": travelport_response
        }

    res_resp = travelport_response.get("ReservationResponse", {})
    reservation = res_resp.get("Reservation", {})
    
    # 1. Extract PNR (Record Locator)
    pnr = None
    receipts = reservation.get("Receipt", [])
    for r in receipts:
        conf = r.get("Confirmation", {})
        loc = conf.get("Locator", {})
        if loc and loc.get("value"):
            pnr = loc.get("value")
            break

    if not pnr:
        pnr = reservation.get("Identifier", {}).get("value") or travelport_response.get("Locator", {}).get("value") or "N/A"

    # 2. Extract Travelers
    travelers = []
    for tr in reservation.get("Traveler", []):
        name_obj = tr.get("PersonName", {})
        given = name_obj.get("Given", "")
        surname = name_obj.get("Surname", "")
        travelers.append({
            "id": tr.get("id"),
            "name": f"{given} {surname}".strip(),
            "passengerType": tr.get("passengerTypeCode", "ADT"),
            "gender": tr.get("gender"),
            "birthDate": tr.get("birthDate")
        })

    # 3. Extract Itinerary / Segments
    segments = []
    for off in reservation.get("Offer", []):
        for prod in off.get("Product", []):
            for fs in prod.get("FlightSegment", []):
                flt = fs.get("Flight", {})
                dep = flt.get("Departure", {})
                arr = flt.get("Arrival", {})
                segments.append({
                    "flightNumber": flt.get("number"),
                    "carrier": flt.get("carrier"),
                    "origin": dep.get("location"),
                    "destination": arr.get("location"),
                    "departureDate": dep.get("date"),
                    "departureTime": dep.get("time"),
                    "arrivalDate": arr.get("date"),
                    "arrivalTime": arr.get("time"),
                    "equipment": flt.get("equipment")
                })

    res_id = reservation.get("Identifier", {}).get("value")

    return {
        "status": "success",
        "pnr": pnr,
        "booking": {
            "pnr": pnr,
            "status": "Confirmed",
            "reservation_id": res_id,
            "travelers": travelers,
            "itinerary": segments,
            "raw": travelport_response
        },
        "data": {
            "pnr": pnr,
            "status": "Confirmed",
            "reservation_id": res_id
        }
    }


def format_pricing_response(travelport_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the Travelport buildfromcatalogproductofferings AirPrice response into
    a standardized structure containing total fare, base fare, taxes, and breakdown.
    """
    offer_list_resp = travelport_response.get("OfferListResponse", {})
    offers = offer_list_resp.get("OfferID", [])
    if not offers:
        offers = travelport_response.get("Offer", [])

    if not offers:
        return {
            "status": "error",
            "message": "No pricing offers returned by Travelport",
            "details": travelport_response
        }

    first_offer = offers[0]
    price_obj = first_offer.get("Price", {})
    currency = price_obj.get("CurrencyCode", {}).get("value", "BDT")
    base_fare = price_obj.get("Base", 0)
    total_taxes = price_obj.get("TotalTaxes", 0)
    total_fare = price_obj.get("TotalPrice", base_fare + total_taxes)

    # Tax breakdown
    tax_breakdown = []
    breakdowns = price_obj.get("PriceBreakdown", [])
    if breakdowns:
        taxes_detail = breakdowns[0].get("Amount", {}).get("Taxes", {})
        for t in taxes_detail.get("Tax", []):
            tax_breakdown.append({
                "code": t.get("taxCode"),
                "amount": t.get("value"),
                "description": t.get("description")
            })

    # Segments
    itinerary = []
    for prod in first_offer.get("Product", []):
        for fs in prod.get("FlightSegment", []):
            flt = fs.get("Flight", {})
            dep = flt.get("Departure", {})
            arr = flt.get("Arrival", {})
            itinerary.append({
                "flightNumber": flt.get("number"),
                "carrier": flt.get("carrier"),
                "origin": dep.get("location"),
                "destination": arr.get("location"),
                "departure": f"{dep.get('date')} {dep.get('time')}".strip(),
                "arrival": f"{arr.get('date')} {arr.get('time')}".strip()
            })

    # Baggage & penalties from TermsAndConditionsFull
    terms = first_offer.get("TermsAndConditionsFull", [])
    baggage_info = []
    penalties_info = {}
    for term in terms:
        for bag in term.get("BaggageAllowance", []):
            items = bag.get("BaggageItem", [])
            txt = items[0].get("Text") if items else ""
            baggage_info.append({
                "type": bag.get("baggageType"),
                "details": txt,
                "pieces": bag.get("Text")
            })
        if "Penalties" in term:
            penalties_info = term.get("Penalties", {})

    return {
        "status": "success",
        "message": "Flight price revalidated successfully",
        "pricing": {
            "total": total_fare,
            "total_fare": total_fare,
            "base": base_fare,
            "base_fare": base_fare,
            "taxes": total_taxes,
            "tax_amount": total_taxes,
            "currency": currency,
            "taxBreakdown": tax_breakdown,
            "baggage": baggage_info,
            "penalties": penalties_info,
            "itinerary": itinerary
        },
        "data": {
            "pricing": {
                "total": total_fare,
                "total_fare": total_fare,
                "base": base_fare,
                "base_fare": base_fare,
                "taxes": total_taxes,
                "tax_amount": total_taxes,
                "currency": currency
            }
        }
    }
