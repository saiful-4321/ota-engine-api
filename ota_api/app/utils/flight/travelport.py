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
    Properly pairs combinable multi-journey (round-trip) offerings while
    preserving one-way offerings seamlessly.
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

    trace_id = travelport_response.get("_trace_id", "")
    transaction_id = root.get("transactionId", "")
    cpo_id = root.get("CatalogProductOfferings", {}).get("Identifier", {}).get("value") or transaction_id

    parsed_items = []

    for idx, off in enumerate(offerings):
        raw_offer_id = off.get("id", f"cpo_{idx}")
        seq = off.get("sequence", 1)
        dep_loc = off.get("Departure", "")
        arr_loc = off.get("Arrival", "")
        options = off.get("ProductBrandOptions", [])

        for opt in options:
            f_refs = opt.get("flightRefs", [])
            flight_objs = [flights_dict[r] for r in f_refs if r in flights_dict]
            if not flight_objs:
                continue

            for pbo in opt.get("ProductBrandOffering", []):
                prod_ref = "p0"
                prods = pbo.get("Product", [])
                if prods and isinstance(prods, list) and isinstance(prods[0], dict):
                    prod_ref = prods[0].get("productRef") or "p0"

                comb_codes = pbo.get("CombinabilityCode", [])
                price_detail = pbo.get("BestCombinablePrice", {})
                total_price_num = price_detail.get("TotalPrice", 0)
                base_fare = price_detail.get("Base", 0)
                taxes = price_detail.get("TotalTaxes", 0)
                currency = price_detail.get("CurrencyCode", {}).get("value", "BDT")

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

                parsed_items.append({
                    "raw_offer_id": raw_offer_id,
                    "seq": seq,
                    "dep_loc": dep_loc,
                    "arr_loc": arr_loc,
                    "prod_ref": prod_ref,
                    "comb_codes": comb_codes,
                    "price_detail": price_detail,
                    "total_price_num": total_price_num,
                    "base_fare": base_fare,
                    "taxes": taxes,
                    "currency": currency,
                    "top_carrier": top_carrier,
                    "top_airline_name": top_airline_name,
                    "stops_list": stops_list,
                    "baggage_summary": baggage_summary,
                    "is_ndc": is_ndc,
                    "leg": leg
                })

    formatted_flights = []

    # Check if this search returned multiple journeys (e.g. sequence 1 and 2 for round-trip)
    seq_set = sorted(list(set(it["seq"] for it in parsed_items if it.get("seq") is not None)))

    # If sequence numbers are identical but routes are opposing, assign sequence 1 and 2
    if len(seq_set) <= 1 and parsed_items:
        first_route = (parsed_items[0]["dep_loc"], parsed_items[0]["arr_loc"])
        for it in parsed_items:
            cur_route = (it["dep_loc"], it["arr_loc"])
            if cur_route != first_route and cur_route == (first_route[1], first_route[0]):
                it["seq"] = 2
            else:
                it["seq"] = 1
        seq_set = sorted(list(set(it["seq"] for it in parsed_items)))

    if len(seq_set) >= 2:
        # Multi-journey (Round-trip / Multi-city) pairing
        s1_items = [it for it in parsed_items if it["seq"] == seq_set[0]]
        s2_items = [it for it in parsed_items if it["seq"] == seq_set[1]]

        from collections import defaultdict
        comb_map_s1 = defaultdict(list)
        comb_map_s2 = defaultdict(list)
        for it in s1_items:
            for c in it["comb_codes"]:
                comb_map_s1[c].append(it)
        for it in s2_items:
            for c in it["comb_codes"]:
                comb_map_s2[c].append(it)

        shared_codes = sorted(list(set(comb_map_s1.keys()) & set(comb_map_s2.keys())))
        seen_pairs = set()

        for c in shared_codes:
            for i1 in comb_map_s1[c]:
                for i2 in comb_map_s2[c]:
                    pair_key = (
                        i1["raw_offer_id"], i2["raw_offer_id"],
                        i1["prod_ref"], i2["prod_ref"],
                        tuple(s["flightNumber"] for s in i1["leg"]["segments"]),
                        tuple(s["flightNumber"] for s in i2["leg"]["segments"])
                    )
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    if trace_id and cpo_id:
                        offer_id = f"{i1['raw_offer_id']},{i2['raw_offer_id']}@@{trace_id}@@{cpo_id}@@{i1['prod_ref']},{i2['prod_ref']}@@{i1['top_carrier']}"
                    elif trace_id:
                        offer_id = f"{i1['raw_offer_id']},{i2['raw_offer_id']}@@{trace_id}@@@@{i1['prod_ref']},{i2['prod_ref']}@@{i1['top_carrier']}"
                    else:
                        offer_id = f"{i1['raw_offer_id']},{i2['raw_offer_id']}"

                    price_det = i1["price_detail"] if i1["total_price_num"] > 0 else i2["price_detail"]
                    total_price_num = price_det.get("TotalPrice", 0)
                    base_fare = price_det.get("Base", 0)
                    taxes = price_det.get("TotalTaxes", 0)
                    currency = price_det.get("CurrencyCode", {}).get("value", "BDT")
                    total_price_str = f"{currency} {total_price_num:,}"

                    is_ndc = i1["is_ndc"] or i2["is_ndc"]
                    top_c = i1["top_carrier"]
                    top_name = i1["top_airline_name"]

                    flight_dict = {
                        "id": offer_id,
                        "tripType": "round-trip",
                        "airline": {
                            "code": top_c,
                            "name": top_name,
                            "logo": f"https://pics.avs.io/al_sha/100/100/{top_c}.png" if top_c else ""
                        },
                        "departure": i1["leg"]["departure"],
                        "arrival": i1["leg"]["arrival"],
                        "duration": i1["leg"]["duration"],
                        "price": total_price_str,
                        "numericPrice": total_price_num,
                        "baseFare": base_fare,
                        "taxes": taxes,
                        "currency": currency,
                        "stops": i1["stops_list"],
                        "journeyDate": i1["leg"]["departure"].get("date", ""),
                        "isRefundable": True,
                        "baggageSummary": i1["baggage_summary"] or i2["baggage_summary"] or "20kg",
                        "seatsRemaining": 9,
                        "validatingCarrier": top_c,
                        "apiProvider": "Travelport",
                        "api_provider": "travelport",
                        "pcc": "3Q3I",
                        "isNdc": is_ndc,
                        "is_ndc": is_ndc,
                        "fareType": "NDC" if is_ndc else "GDS",
                        "fare_type": "NDC" if is_ndc else "GDS",
                        "tags": ["NDC"] if is_ndc else [],
                        "contentSource": "NDC" if is_ndc else "GDS",
                        "legs": [i1["leg"], i2["leg"]]
                    }
                    formatted_flights.append(flight_dict)

        # Fallback if no shared combinability codes: pair by matching carrier
        if not formatted_flights:
            carrier_map_s2 = defaultdict(list)
            for it in s2_items:
                carrier_map_s2[it["top_carrier"]].append(it)

            for i1 in s1_items:
                candidates = carrier_map_s2.get(i1["top_carrier"], s2_items)
                if not candidates:
                    continue
                i2 = candidates[0]
                if trace_id and cpo_id:
                    offer_id = f"{i1['raw_offer_id']},{i2['raw_offer_id']}@@{trace_id}@@{cpo_id}@@{i1['prod_ref']},{i2['prod_ref']}@@{i1['top_carrier']}"
                elif trace_id:
                    offer_id = f"{i1['raw_offer_id']},{i2['raw_offer_id']}@@{trace_id}@@@@{i1['prod_ref']},{i2['prod_ref']}@@{i1['top_carrier']}"
                else:
                    offer_id = f"{i1['raw_offer_id']},{i2['raw_offer_id']}"

                price_det = i1["price_detail"] if i1["total_price_num"] > 0 else i2["price_detail"]
                total_price_num = price_det.get("TotalPrice", 0)
                base_fare = price_det.get("Base", 0)
                taxes = price_det.get("TotalTaxes", 0)
                currency = price_det.get("CurrencyCode", {}).get("value", "BDT")
                total_price_str = f"{currency} {total_price_num:,}"

                is_ndc = i1["is_ndc"] or i2["is_ndc"]
                top_c = i1["top_carrier"]
                top_name = i1["top_airline_name"]

                formatted_flights.append({
                    "id": offer_id,
                    "tripType": "round-trip",
                    "airline": {
                        "code": top_c,
                        "name": top_name,
                        "logo": f"https://pics.avs.io/al_sha/100/100/{top_c}.png" if top_c else ""
                    },
                    "departure": i1["leg"]["departure"],
                    "arrival": i1["leg"]["arrival"],
                    "duration": i1["leg"]["duration"],
                    "price": total_price_str,
                    "numericPrice": total_price_num,
                    "baseFare": base_fare,
                    "taxes": taxes,
                    "currency": currency,
                    "stops": i1["stops_list"],
                    "journeyDate": i1["leg"]["departure"].get("date", ""),
                    "isRefundable": True,
                    "baggageSummary": i1["baggage_summary"] or i2["baggage_summary"] or "20kg",
                    "seatsRemaining": 9,
                    "validatingCarrier": top_c,
                    "apiProvider": "Travelport",
                    "api_provider": "travelport",
                    "pcc": "3Q3I",
                    "isNdc": is_ndc,
                    "is_ndc": is_ndc,
                    "fareType": "NDC" if is_ndc else "GDS",
                    "fare_type": "NDC" if is_ndc else "GDS",
                    "tags": ["NDC"] if is_ndc else [],
                    "contentSource": "NDC" if is_ndc else "GDS",
                    "legs": [i1["leg"], i2["leg"]]
                })

    # If single sequence (one-way) or still unformatted, emit as single-leg flights
    if not formatted_flights:
        for it in parsed_items:
            top_c = it["top_carrier"]
            if trace_id and cpo_id:
                offer_id = f"{it['raw_offer_id']}@@{trace_id}@@{cpo_id}@@{it['prod_ref']}@@{top_c}"
            elif trace_id:
                offer_id = f"{it['raw_offer_id']}@@{trace_id}@@@@{it['prod_ref']}@@{top_c}"
            else:
                offer_id = it["raw_offer_id"]

            total_price_num = it["total_price_num"]
            base_fare = it["base_fare"]
            taxes = it["taxes"]
            currency = it["currency"]
            total_price_str = f"{currency} {total_price_num:,}"
            top_name = it["top_airline_name"]

            formatted_flights.append({
                "id": offer_id,
                "tripType": "one-way",
                "airline": {
                    "code": top_c,
                    "name": top_name,
                    "logo": f"https://pics.avs.io/al_sha/100/100/{top_c}.png" if top_c else ""
                },
                "departure": it["leg"]["departure"],
                "arrival": it["leg"]["arrival"],
                "duration": it["leg"]["duration"],
                "price": total_price_str,
                "numericPrice": total_price_num,
                "baseFare": base_fare,
                "taxes": taxes,
                "currency": currency,
                "stops": it["stops_list"],
                "journeyDate": it["leg"]["departure"].get("date", ""),
                "isRefundable": True,
                "baggageSummary": it["baggage_summary"],
                "seatsRemaining": 9,
                "validatingCarrier": top_c,
                "apiProvider": "Travelport",
                "api_provider": "travelport",
                "pcc": "3Q3I",
                "isNdc": it["is_ndc"],
                "is_ndc": it["is_ndc"],
                "fareType": "NDC" if it["is_ndc"] else "GDS",
                "fare_type": "NDC" if it["is_ndc"] else "GDS",
                "tags": ["NDC"] if it["is_ndc"] else [],
                "contentSource": "NDC" if it["is_ndc"] else "GDS",
                "legs": [it["leg"]]
            })

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


def format_ticketing_response(travelport_response: Dict[str, Any]) -> Dict[str, Any]:
    """Normalized ticketing result (same shape as the Sabre formatter)."""
    tickets = [
        str(t.get("TicketNumber")) for t in travelport_response.get("TicketDetails", [])
        if isinstance(t, dict) and t.get("TicketNumber")
    ]
    ok = str(travelport_response.get("status", "")).lower() == "success" and bool(tickets)
    return {
        "status": "success" if ok else "error",
        "message": "Tickets issued successfully" if ok else "Ticketing failed",
        "ticketing": {
            "status": travelport_response.get("status"),
            "pnr": travelport_response.get("pnr"),
            "errors": [],
            "timestamp": None,
            "ticket_numbers": tickets,
        },
    }


def format_cancel_response(travelport_response: Dict[str, Any]) -> Dict[str, Any]:
    pnr = travelport_response.get("pnr")
    return {
        "status": "success",
        "message": f"Itinerary {pnr} has been successfully cancelled.",
        "cancellation": {
            "pnr": pnr,
            "cancelledAt": None,
            "cancelledAll": True,
            "cancelledSegments": [],
        },
    }
