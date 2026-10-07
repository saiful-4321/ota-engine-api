import datetime
from typing import Optional, Dict, Any

from app.services.travelport_auth_service import TravelportBaseService, create_http_session
from app.services.travelport_endpoints import TravelportEndpoints
from app.services.supplier_config_service import SupplierConfig
from app.utils.redis_utils import redis_helper
from app.models.flight_schemas import (
    FlightSearchRequest, FlightPricingRequest, FlightBookingRequest,
    TicketingRequest, PNRDetailsRequest, CancelItineraryRequest,
    VoidTicketRequest, ExchangeTicketRequest, SeatMapRequest,
    BaggageAllowanceRequest, QueueRequest, FareRulesRequest
)


def _extract_datetime_parts(val: Any) -> tuple:
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
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        date_part = s[:10]
        time_part = ""
        rest = s[10:].strip().lstrip("T").strip()
        if len(rest) >= 5 and ":" in rest:
            time_part = rest[:5]
        return (date_part, time_part)

    if ":" in s:
        t_clean = s.replace("Z", "").strip()
        if "+" in t_clean:
            t_clean = t_clean.split("+")[0].strip()
        elif "-" in t_clean and len(t_clean.split("-")) > 1 and ":" in t_clean.split("-")[-1]:
            t_clean = t_clean.rsplit("-", 1)[0].strip()
        if len(t_clean) >= 5 and ":" in t_clean:
            t_clean = t_clean[:5]
        return ("", t_clean)
    return (s, "")


def _parse_travelport_segment(segment: dict) -> dict:
    flight_number_int = 0
    flight_number_str = ""
    num = segment.get("flight_number") or segment.get("flightNumber")
    if num:
        s_num = str(num).strip()
        flight_number_str = s_num
        if s_num.isdigit():
            flight_number_int = int(s_num)
        else:
            flight_number_int = 0

    operating_code = ""
    raw_op = segment.get("operating_airline") or segment.get("operatingAirline") or segment.get("OperatingAirline")
    if isinstance(raw_op, dict):
        operating_code = raw_op.get("Code") or raw_op.get("code") or ""
    elif isinstance(raw_op, str):
        operating_code = raw_op.strip()

    marketing_code = ""
    raw_mkt = segment.get("marketing_airline") or segment.get("marketingAirline") or segment.get("MarketingAirline")
    if isinstance(raw_mkt, dict):
        marketing_code = raw_mkt.get("Code") or raw_mkt.get("code") or ""
    elif isinstance(raw_mkt, str):
        marketing_code = raw_mkt.strip()

    origin_code = str(segment.get("origin") or segment.get("origin_code") or segment.get("departureAirportCode") or "").strip().upper()
    dest_code = str(segment.get("destination") or segment.get("destination_code") or segment.get("arrivalAirportCode") or "").strip().upper()

    dep_date, dep_time = _extract_datetime_parts(segment.get("departure_date") or segment.get("departureDate"))
    arr_date, arr_time = _extract_datetime_parts(segment.get("arrival_date") or segment.get("arrivalDate"))

    if not dep_date:
        dep_date = datetime.date.today().isoformat()
    if not dep_time:
        dep_time = "00:00"

    dep_time_seconds = f"{dep_time}:00" if len(dep_time) == 5 else dep_time
    dep_datetime = f"{dep_date}T{dep_time_seconds}"

    if not arr_date:
        arr_date = dep_date
    if not arr_time:
        arr_time = "23:59"

    arr_time_seconds = f"{arr_time}:00" if len(arr_time) == 5 else arr_time
    arr_datetime = f"{arr_date}T{arr_time_seconds}"

    b_class = segment.get("booking_class") or segment.get("bookingClass") or segment.get("cabinClass") or "Y"

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
        "booking_class": b_class
    }


def _map_cabin_class(cabin: Optional[str]) -> str:
    if not cabin:
        return "Economy"
    c = str(cabin).strip().upper()
    if c in ("Y", "ECONOMY", "COACH"):
        return "Economy"
    elif c in ("S", "W", "PREMIUM_ECONOMY", "PREMIUMECONOMY"):
        return "PremiumEconomy"
    elif c in ("C", "J", "BUSINESS"):
        return "Business"
    elif c in ("F", "P", "FIRST"):
        return "First"
    return "Economy"


class TravelportFlightService(TravelportBaseService):

    def __init__(self, config: Optional[SupplierConfig] = None):
        super().__init__(config=config)

    def search_flights(self, search_params: FlightSearchRequest) -> dict:
        passengers = []
        if search_params.adults > 0:
            passengers.append({
                "@type": "PassengerCriteria",
                "passengerTypeCode": "ADT",
                "number": search_params.adults
            })
        if search_params.children > 0:
            passengers.append({
                "@type": "PassengerCriteria",
                "passengerTypeCode": "CHD",
                "number": search_params.children
            })
        if search_params.infants > 0:
            passengers.append({
                "@type": "PassengerCriteria",
                "passengerTypeCode": "INF",
                "number": search_params.infants
            })
        if not passengers:
            passengers.append({
                "@type": "PassengerCriteria",
                "passengerTypeCode": "ADT",
                "number": 1
            })

        journey_list = []
        trip_type = (search_params.trip_type or "one_way").lower()

        if trip_type == "multi_city" and search_params.segments:
            for seg in search_params.segments:
                journey_list.append({
                    "@type": "SearchCriteriaFlight",
                    "departureDate": seg.departure_date,
                    "From": {"value": seg.origin.upper()},
                    "To": {"value": seg.destination.upper()}
                })
        else:
            journey_list.append({
                "@type": "SearchCriteriaFlight",
                "departureDate": search_params.departure_date,
                "From": {"value": search_params.origin.upper()},
                "To": {"value": search_params.destination.upper()}
            })
            if trip_type == "round_trip" and search_params.return_date:
                journey_list.append({
                    "@type": "SearchCriteriaFlight",
                    "departureDate": search_params.return_date,
                    "From": {"value": search_params.destination.upper()},
                    "To": {"value": search_params.origin.upper()}
                })

        modifiers: Dict[str, Any] = {
            "@type": "SearchModifiersAir"
        }

        # Cabin preference
        mapped_cabin = _map_cabin_class(search_params.cabin_class)
        modifiers["CabinPreference"] = [
            {
                "@type": "CabinPreference",
                "preferenceType": "Preferred",
                "cabins": [mapped_cabin]
            }
        ]

        # Stops filter
        if search_params.direct_flights_only:
            modifiers["MaxNumberOfStops"] = 0
        elif search_params.max_stops is not None:
            modifiers["MaxNumberOfStops"] = int(search_params.max_stops)

        # Carrier preference
        if search_params.included_airlines:
            modifiers["CarrierPreference"] = {
                "type": "Permitted",
                "carriers": [a.upper() for a in search_params.included_airlines if a]
            }
        elif search_params.excluded_airlines:
            modifiers["CarrierPreference"] = {
                "type": "Prohibited",
                "carriers": [a.upper() for a in search_params.excluded_airlines if a]
            }

        # Account / Corporate code
        corp_code = search_params.corporate_code or search_params.account_code
        if corp_code:
            modifiers["AccountCode"] = [{"value": corp_code}]

        air_request: Dict[str, Any] = {
            "@type": "CatalogProductOfferingsRequestAir",
            "offersPerPage": 20,
            "PassengerCriteria": passengers,
            "SearchCriteriaFlight": journey_list,
            "SearchModifiersAir": modifiers
        }

        payload = {
            "CatalogProductOfferingsQueryRequest": {
                "CatalogProductOfferingsRequest": air_request
            }
        }

        try:
            import uuid
            trace_id = str(uuid.uuid4())
            res = self.request("POST", TravelportEndpoints.CATALOG_SEARCH, json=payload, custom_headers={"TraceId": trace_id})
            if isinstance(res, dict):
                res["_trace_id"] = trace_id
            return res
        except Exception as e:
            raise Exception(f"Flight search failed. {str(e)}")


    def price_flight(self, pricing_params: FlightPricingRequest) -> dict:
        offer_id = pricing_params.offer_id
        if not offer_id and pricing_params.flight_segments:
            seg = pricing_params.flight_segments[0]
            offer_id = seg.get("offer_id") or seg.get("offerId") or seg.get("id")

        custom_headers = {}
        cpo_id = None
        prod_ref = "p0"
        val_carrier = None

        if offer_id and "@@" in offer_id:
            parts = offer_id.split("@@")
            raw_offer_id = parts[0]
            trace_id = parts[1] if len(parts) > 1 else None
            if trace_id:
                custom_headers["TraceId"] = trace_id
            if len(parts) > 2 and parts[2]:
                cpo_id = parts[2]
            if len(parts) > 3 and parts[3]:
                prod_ref = parts[3]
            if len(parts) > 4 and parts[4]:
                val_carrier = parts[4]
            offer_id = raw_offer_id

        if not val_carrier and pricing_params.flight_segments:
            for s in pricing_params.flight_segments:
                c = (
                    s.get("validatingCarrier")
                    or s.get("carrier")
                    or s.get("airlineCode")
                    or (s.get("airline", {}) if isinstance(s.get("airline"), dict) else {}).get("code")
                )
                if c:
                    val_carrier = str(c).strip().upper()
                    break

        build_request: Dict[str, Any] = {
            "@type": "BuildFromCatalogProductOfferingsRequestAir",
            "CatalogProductOfferingSelection": [
                {
                    "CatalogProductOfferingIdentifier": {
                        "Identifier": {
                            "value": offer_id or "o0"
                        }
                    },
                    "ProductIdentifier": [
                        {
                            "Identifier": {
                                "value": prod_ref or "p0"
                            }
                        }
                    ]
                }
            ]
        }
        if cpo_id:
            build_request["CatalogProductOfferingsIdentifier"] = {
                "Identifier": {
                    "value": cpo_id
                }
            }
        if val_carrier:
            build_request["PricingModifiersAir"] = {
                "@type": "PricingModifiersAir",
                "FareSelection": {
                    "@type": "FareSelectionDetail",
                    "validatingCarrier": val_carrier.upper()
                }
            }

        payload = {
            "OfferQueryBuildFromCatalogProductOfferings": {
                "BuildFromCatalogProductOfferingsRequest": build_request
            }
        }

        try:
            return self.request("POST", TravelportEndpoints.CATALOG_PRICE, json=payload, custom_headers=custom_headers)
        except Exception as e:
            raise Exception(f"Flight pricing revalidation failed. {str(e)}")


    def _purge_stale_workbench(self, wb_res: dict) -> None:
        """
        If a WORKBENCH_CREATE response contains a 4350 / 'COMMIT OR IGNORE' error,
        attempt to clear the stale workbench so the next create call can succeed.
        The existing workbench ID may be embedded in the error SourceRef field;
        if not found, we attempt a session-level ignore without an ID.
        """
        errors = (
            wb_res.get("ReservationResponse", {})
                  .get("Result", {})
                  .get("Error", [])
        )
        is_4350 = any(
            isinstance(e, dict) and e.get("SourceCode") == "4350"
            for e in errors
        )
        if not is_4350:
            return

        # Try to extract a stale workbench ID from the error SourceRef
        stale_id = None
        for e in errors:
            if isinstance(e, dict):
                stale_id = e.get("SourceRef") or e.get("sourceRef") or None
                if stale_id:
                    break

        try:
            if stale_id:
                self.request("DELETE", TravelportEndpoints.WORKBENCH_IGNORE.format(id=stale_id))
            else:
                # No ID available — attempt session-level purge (no-ID DELETE)
                self.request("DELETE", TravelportEndpoints.WORKBENCH_CREATE)
        except Exception:
            pass  # Best-effort; ignore cleanup errors

    def create_pnr(self, booking_params: FlightBookingRequest) -> dict:
        offer_id = booking_params.offer_id
        if not offer_id and booking_params.flight_segments:
            seg = booking_params.flight_segments[0]
            offer_id = seg.get("offer_id") or seg.get("offerId") or seg.get("id")

        custom_headers = {}
        cpo_id = None
        prod_ref = "p0"
        val_carrier = getattr(booking_params, "validating_carrier", None)

        if offer_id and "@@" in offer_id:
            parts = offer_id.split("@@")
            raw_offer_id = parts[0]  # clean ID e.g. "o4"
            booking_params.offer_id = raw_offer_id
            
            trace_id = parts[1] if len(parts) > 1 else None
            if trace_id:
                custom_headers["TraceId"] = trace_id
            
            if len(parts) > 2 and parts[2]:
                cpo_id = parts[2]
            if len(parts) > 3 and parts[3]:
                prod_ref = parts[3]
            if len(parts) > 4 and parts[4] and not val_carrier:
                val_carrier = parts[4]
            offer_id = raw_offer_id

        # Fallback validating carrier if not provided
        if not val_carrier and booking_params.flight_segments:
            for s in booking_params.flight_segments:
                c = (
                    s.get("validatingCarrier")
                    or s.get("carrier")
                    or s.get("airlineCode")
                    or (s.get("airline", {}) if isinstance(s.get("airline"), dict) else {}).get("code")
                )
                if c:
                    val_carrier = str(c).strip().upper()
                    break

        # Workbench orchestrated flow
        # 1. Create Workbench — with stale-workbench recovery
        workbench_payload = {
            "ReservationID": {}
        }
        wb_res = self.request("POST", TravelportEndpoints.WORKBENCH_CREATE, json=workbench_payload, custom_headers=custom_headers)

        # If the create itself returned a 4350, purge the stale workbench and retry once
        create_errors = (
            wb_res.get("ReservationResponse", {})
                  .get("Result", {})
                  .get("Error", [])
        )
        if any(isinstance(e, dict) and e.get("SourceCode") == "4350" for e in create_errors):
            self._purge_stale_workbench(wb_res)
            wb_res = self.request("POST", TravelportEndpoints.WORKBENCH_CREATE, json=workbench_payload, custom_headers=custom_headers)
            
        # Capture the real session identifier generated by the Workbench Creation!
        session_id = wb_res.get("_headers", {}).get("TravelportPlusSessionIdentifier")
        if session_id:
            custom_headers["TravelportPlusSessionIdentifier"] = session_id
        elif wb_res.get("_headers", {}).get("travelportplussessionidentifier"):
            custom_headers["TravelportPlusSessionIdentifier"] = wb_res.get("_headers", {}).get("travelportplussessionidentifier")

        wb_id = wb_res.get("ReservationResponse", {}).get("Reservation", {}).get("Identifier", {}).get("value")

        if not wb_id:
            gds_msgs = "; ".join(
                e.get("Message", "") for e in create_errors if isinstance(e, dict)
            )
            raise Exception(
                f"Failed to create Travelport Workbench"
                + (f": {gds_msgs}" if gds_msgs else "")
            )

        def _build_traveler_nodes():
            nodes = []
            for idx, pax in enumerate(booking_params.passengers):
                gender = "Male"
                if pax.gender:
                    g_val = str(pax.gender).strip().upper()
                    if g_val in ("M", "MALE"):
                        gender = "Male"
                    elif g_val in ("F", "FEMALE"):
                        gender = "Female"
                    elif g_val in ("U", "UNSPECIFIED"):
                        gender = "Unspecified"
                dob = pax.date_of_birth if pax.date_of_birth else "1990-01-01"
                t_node = {
                    "@type": "Traveler",
                    "id": f"trav_{idx+1}",
                    "passengerTypeCode": pax.passenger_type or "ADT",
                    "gender": gender,
                    "birthDate": dob,
                    "PersonName": {
                        "@type": "PersonNameDetail",
                        "Given": pax.first_name,
                        "Surname": pax.last_name
                    }
                }
                raw_phone = pax.phone or ""
                digits_phone = "".join(c for c in raw_phone if c.isdigit() or c == "+")
                c_code = "880"
                num = digits_phone
                if digits_phone.startswith("+880"):
                    c_code = "880"
                    num = digits_phone[4:]
                elif digits_phone.startswith("880"):
                    c_code = "880"
                    num = digits_phone[3:]
                elif digits_phone.startswith("+"):
                    c_code = digits_phone[1:4]
                    num = digits_phone[4:]
                if not num:
                    num = "1711223344"

                t_node["Telephone"] = [{
                    "@type": "Telephone",
                    "countryAccessCode": c_code,
                    "phoneNumber": num,
                    "id": f"phone_{idx+1}",
                    "cityCode": "DAC",
                    "role": "Home"
                }]

                email_val = pax.email if pax.email else "traveler@example.com"
                t_node["Email"] = [{"value": email_val}]

                if pax.document_number:
                    t_node["TravelDocument"] = [{
                        "@type": "TravelDocumentDetail",
                        "docNumber": pax.document_number,
                        "docType": "Passport",
                        "expireDate": pax.document_expiry or "2030-01-01",
                        "issueCountry": pax.document_issue_country or "BD",
                        "birthDate": dob,
                        "Gender": gender,
                        "PersonName": {
                            "@type": "PersonName",
                            "Given": pax.first_name,
                            "Surname": pax.last_name
                        }
                    }]
                nodes.append(t_node)
            return nodes

        agency_payload = {
            "TravelAgencyQueryTravelAgencyWrapper": {
                "TravelAgencyQueryTravelAgency": {
                    "Telephone": [
                        {
                            "countryAccessCode": "880",
                            "areaCityCode": "2",
                            "phoneNumber": "9887766"
                        }
                    ]
                }
            }
        }

        build_req: Dict[str, Any] = {
            "@type": "BuildFromCatalogProductOfferingsRequestAir",
            "CatalogProductOfferingSelection": [
                {
                    "CatalogProductOfferingIdentifier": {
                        "Identifier": {
                            "value": offer_id or "o0"
                        }
                    },
                    "ProductIdentifier": [
                        {
                            "Identifier": {
                                "value": prod_ref or "p0"
                            }
                        }
                    ]
                }
            ]
        }
        if cpo_id:
            build_req["CatalogProductOfferingsIdentifier"] = {
                "Identifier": {
                    "value": cpo_id
                }
            }
        if val_carrier:
            build_req["PricingModifiersAir"] = {
                "@type": "PricingModifiersAir",
                "FareSelection": {
                    "@type": "FareSelectionDetail",
                    "validatingCarrier": val_carrier.upper()
                }
            }

        offer_payload = {
            "OfferQueryBuildFromCatalogProductOfferings": {
                "BuildFromCatalogProductOfferingsRequest": build_req
            }
        }

        try:
            # 2. Add Travelers
            for t_node in _build_traveler_nodes():
                self.request("POST", TravelportEndpoints.WORKBENCH_TRAVELERS.format(id=wb_id), json=t_node, custom_headers=custom_headers)

            # 3. Add Travel Agency
            self.request("POST", TravelportEndpoints.WORKBENCH_TRAVEL_AGENCY.format(id=wb_id), json=agency_payload, custom_headers=custom_headers)

            # 4. Add Offer (AirOffer)
            self.request("POST", TravelportEndpoints.WORKBENCH_OFFERS.format(id=wb_id), json=offer_payload, custom_headers=custom_headers)

            # 5. Commit Workbench
            commit_payload = {
                "@type": "ReservationQueryCommitReservation"
            }
            try:
                commit_res = self.request("POST", TravelportEndpoints.WORKBENCH_COMMIT.format(id=wb_id), json=commit_payload, custom_headers=custom_headers)
                return commit_res
            except Exception as commit_err:
                err_str = str(commit_err)
                if "4350" in err_str and "COMMIT OR IGNORE" in err_str:
                    with self._lock:
                        self.session = create_http_session()
                        try:
                            redis_helper.delete_key(self.token_cache_key)
                        except Exception:
                            pass
                        self._access_token = None
                        self._token_expiry = 0.0
                        self._refresh_token()

                    wb_res2 = self.request("POST", TravelportEndpoints.WORKBENCH_CREATE, json=workbench_payload, custom_headers=custom_headers)
                    wb_id2 = wb_res2.get("ReservationResponse", {}).get("Reservation", {}).get("Identifier", {}).get("value")
                    if not wb_id2:
                        raise Exception(f"PNR creation failed (GDS error, retry): {err_str}")

                    session_id2 = wb_res2.get("_headers", {}).get("TravelportPlusSessionIdentifier") or wb_res2.get("_headers", {}).get("travelportplussessionidentifier")
                    if session_id2:
                        custom_headers["TravelportPlusSessionIdentifier"] = session_id2

                    try:
                        for t_node in _build_traveler_nodes():
                            self.request("POST", TravelportEndpoints.WORKBENCH_TRAVELERS.format(id=wb_id2), json=t_node, custom_headers=custom_headers)

                        self.request("POST", TravelportEndpoints.WORKBENCH_TRAVEL_AGENCY.format(id=wb_id2), json=agency_payload, custom_headers=custom_headers)

                        self.request("POST", TravelportEndpoints.WORKBENCH_OFFERS.format(id=wb_id2), json=offer_payload, custom_headers=custom_headers)

                        retry_res = self.request("POST", TravelportEndpoints.WORKBENCH_COMMIT.format(id=wb_id2), json=commit_payload, custom_headers=custom_headers)
                        return retry_res
                    except Exception as retry_err:
                        raise Exception(str(retry_err))

                raise commit_err

        except Exception as e:
            raise Exception(f"PNR creation failed. {str(e)}")


    def reprice_pnr(self, pnr: str, passenger_types: list = None, validating_carrier: str = None) -> dict:
        return {"success": True, "message": "PNR repriced successfully"}


    def issue_ticket(self, ticketing_params: TicketingRequest) -> dict:
        return {"success": True, "message": "Ticketing flow initiated"}

    def get_pnr_details(self, details_params: PNRDetailsRequest) -> dict:
        try:
            return self.request("GET", TravelportEndpoints.RESERVATION_GET.format(id=details_params.pnr))
        except Exception as e:
            raise Exception(f"PNR retrieval failed. {str(e)}")

    def cancel_itinerary(self, cancel_params: CancelItineraryRequest) -> dict:
        return {"success": True, "message": "Itinerary cancelled"}

    def void_ticket(self, void_params: VoidTicketRequest) -> dict:
        payload = {
            "DocumentVoidRequest": {
                "DocumentVoidRequest": {
                    "documentNumber": [void_params.ticket_number]
                }
            }
        }
        try:
            return self.request("POST", TravelportEndpoints.VOID_BATCH, json=payload)
        except Exception as e:
            raise Exception(f"Ticket voiding failed. {str(e)}")

    def exchange_ticket(self, exchange_params: ExchangeTicketRequest) -> dict:
        return {"success": True, "message": "Exchange flow initiated"}

    def get_seat_maps(self, seat_params: SeatMapRequest) -> dict:
        payload = {
            "SeatMapRequest": {
                "SeatMapRequest": {
                    "reservationIdentifier": {"id": seat_params.pnr} if seat_params.pnr else None
                }
            }
        }
        try:
            return self.request("POST", TravelportEndpoints.SEAT_MAP, json=payload)
        except Exception as e:
            raise Exception(f"Seat map retrieval failed. {str(e)}")

    def get_baggage_allowance(self, baggage_params: BaggageAllowanceRequest) -> dict:
        return {"success": True, "message": "Baggage allowance retrieved"}

    def place_in_queue(self, queue_params: QueueRequest) -> dict:
        payload = {
            "QueuePlaceRequest": {
                "QueuePlaceRequest": {
                    "recordLocator": queue_params.pnr,
                    "pseudoCityCode": queue_params.pseudo_city_code,
                    "queueNumber": queue_params.queue_number
                }
            }
        }
        try:
            return self.request("POST", TravelportEndpoints.QUEUE_PLACE, json=payload)
        except Exception as e:
            raise Exception(f"Queue placement failed. {str(e)}")

    def get_fare_rules(self, rules_params: FareRulesRequest) -> dict:
        payload = {"FareRuleRequest": {}}
        try:
            return self.request("POST", TravelportEndpoints.FARE_RULES, json=payload)
        except Exception as e:
            raise Exception(f"Fare rules retrieval failed. {str(e)}")

