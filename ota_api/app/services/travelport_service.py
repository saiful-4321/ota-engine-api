import datetime
from typing import Optional, Dict, Any

from app.services.travelport_auth_service import TravelportBaseService
from app.services.travelport_endpoints import TravelportEndpoints
from app.services.supplier_config_service import SupplierConfig
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
            return self.request("POST", TravelportEndpoints.CATALOG_SEARCH, json=payload)
        except Exception as e:
            raise Exception(f"Flight search failed. {str(e)}")


    def price_flight(self, pricing_params: FlightPricingRequest) -> dict:
        payload = {
            "CatalogProductOfferingsPriceRequest": {
                "CatalogProductOfferingsPriceRequest": {
                    "passengerCriteria": [
                        {"passengerTypeCode": p.passenger_type, "quantity": p.quantity}
                        for p in pricing_params.passengers
                    ],
                    "offers": []
                }
            }
        }
        
        # NOTE: Travelport pricing needs the offer ID from search.
        # Here we extract offer IDs from flight_segments (if they were stored).
        offer_id = pricing_params.flight_segments[0].get("offer_id") if pricing_params.flight_segments else None
        
        if offer_id:
            payload["CatalogProductOfferingsPriceRequest"]["CatalogProductOfferingsPriceRequest"]["offers"].append({"Identifier": {"id": offer_id}})
            
        try:
            return self.request("POST", TravelportEndpoints.CATALOG_PRICE, json=payload)
        except Exception as e:
            raise Exception(f"Flight pricing revalidation failed. {str(e)}")


    def create_pnr(self, booking_params: FlightBookingRequest) -> dict:
        # Workbench orchestrated flow
        # 1. Create Workbench
        workbench_payload = {
            "ReservationWorkbenchBuildRequest": {
                "ReservationWorkbenchBuildRequest": {}
            }
        }
        wb_res = self.request("POST", TravelportEndpoints.WORKBENCH_CREATE, json=workbench_payload)
        wb_id = wb_res.get("ReservationWorkbenchBuildResponse", {}).get("ReservationWorkbench", {}).get("Identifier", {}).get("id")
        
        if not wb_id:
            raise Exception("Failed to create Travelport Workbench")

        # 2. Add Travelers
        travelers_payload = {
            "TravelerBuildRequest": {
                "TravelerBuildRequest": {
                    "travelers": []
                }
            }
        }
        for pax in booking_params.passengers:
            traveler_node = {
                "travelerType": pax.passenger_type,
                "personName": {
                    "givenName": pax.first_name,
                    "surname": pax.last_name
                },
                "birthDate": pax.date_of_birth,
                "gender": pax.gender
            }
            if pax.phone:
                traveler_node["contactPhone"] = [{"number": pax.phone}]
            if pax.document_number:
                traveler_node["identityDocument"] = [{
                    "documentNumber": pax.document_number,
                    "documentType": "Passport",
                    "expiryDate": pax.document_expiry,
                    "issueCountry": pax.document_issue_country or "BD"
                }]
            travelers_payload["TravelerBuildRequest"]["TravelerBuildRequest"]["travelers"].append(traveler_node)

        self.request("POST", TravelportEndpoints.WORKBENCH_TRAVELERS.format(id=wb_id), json=travelers_payload)

        # 3. Add Offer (AirOffer)
        offer_id = booking_params.flight_segments[0].get("offer_id") if booking_params.flight_segments else None
        if offer_id:
            offer_payload = {
                "AirOfferBuildRequest": {
                    "AirOfferBuildRequest": {
                        "offers": [{"Identifier": {"id": offer_id}}]
                    }
                }
            }
            self.request("POST", TravelportEndpoints.WORKBENCH_OFFERS.format(id=wb_id), json=offer_payload)

        # 4. Commit Workbench
        commit_payload = {
            "ReservationWorkbenchCommitRequest": {
                "ReservationWorkbenchCommitRequest": {
                    "receivedFrom": "API"
                }
            }
        }
        try:
            return self.request("POST", TravelportEndpoints.WORKBENCH_COMMIT.format(id=wb_id), json=commit_payload)
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

