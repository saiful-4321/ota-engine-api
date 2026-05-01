import json
import re
import requests
from app.services.sabre_auth_service import SabreBaseService
from app.models.sabre_schemas import (
    FlightSearchRequest, FlightPricingRequest, FlightBookingRequest, TicketingRequest,
    PNRDetailsRequest, CancelItineraryRequest, VoidTicketRequest, ExchangeTicketRequest,
    SeatMapRequest, BaggageAllowanceRequest, QueueRequest, FareRulesRequest
)
from app.services.sabre_endpoints import SabreEndpoints
from config import SABRE_PCC

class SabreFlightService(SabreBaseService):
    
    def search_flights(self, search_params: FlightSearchRequest) -> dict:
        """
        Calls Sabre's Bargain Finder Max (BFM) API to search for flights.
        """
        url = f"{self.base_url}{SabreEndpoints.BARGAIN_FINDER_MAX}"
        headers = self.get_headers()
        
        # BFM Request Payload Structure Construction
        # This is a minimal basic structure for connecting.
        payload = {
            "OTA_AirLowFareSearchRQ": {
                "Version": "4.3.0",
                "POS": {
                    "Source": [
                        {
                            "PseudoCityCode": SABRE_PCC,
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
                "OriginDestinationInformation": [
                    {
                        "RPH": "1",
                        "DepartureDateTime": search_params.departure_date + "T00:00:00",
                        "OriginLocation": {
                            "LocationCode": search_params.origin
                        },
                        "DestinationLocation": {
                            "LocationCode": search_params.destination
                        }
                    }
                ],
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
        # Sabre BFM v5: use TravelPreferences.FlightTypePref boolean flags.
        #   direct_flights_only => NonStopOnly: True  (strictly 0 stops)
        #   max_stops == 1      => DirectAndNonStop: True (0 or 1 stop)
        #   max_stops > 1       => no stop restriction applied
        if search_params.direct_flights_only or search_params.max_stops is not None:
            flight_type_pref = {}
            stop_qty = 0 if search_params.direct_flights_only else search_params.max_stops

            if stop_qty == 0:
                flight_type_pref["NonStopOnly"] = True
            elif stop_qty == 1:
                flight_type_pref["DirectAndNonStop"] = True
            # For max_stops > 1 we don't add a restriction — Sabre returns all options

            if flight_type_pref:
                if "TravelPreferences" not in payload["OTA_AirLowFareSearchRQ"]:
                    payload["OTA_AirLowFareSearchRQ"]["TravelPreferences"] = {}
                payload["OTA_AirLowFareSearchRQ"]["TravelPreferences"]["FlightTypePref"] = flight_type_pref

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

        # 4. Corporate & Account Codes (Private Fares)
        # Sabre BFM v5: PriceRequestInformation belongs under TravelerInfoSummary.
        # NegotiatedFareCode must match pattern [A-Za-z]{3}[0-9]{2} (e.g. "ABC12").
        _neg_fare_pattern = re.compile(r'^[A-Za-z]{3}[0-9]{2}$')

        if search_params.corporate_code or search_params.account_code:
            price_req = payload["OTA_AirLowFareSearchRQ"]["TravelerInfoSummary"].setdefault(
                "PriceRequestInformation", {}
            )

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
        
         # Handle Return flight dynamically
        if search_params.return_date:
             payload["OTA_AirLowFareSearchRQ"]["OriginDestinationInformation"].append({
                 "RPH": "2",
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
        Calls Sabre's Enhanced Air Ticket API to price a specifically selected flight.
        """
        # Sabre Revalidate/Pricing Endpoint
        url = f"{self.base_url}{SabreEndpoints.ENHANCED_AIR_TICKET_PRICE}"
        headers = self.get_headers()
        
        # We need a transformation layer here to map `FlightPricingRequest` input
        # into a Sabre standard pricing payload. (Simplifying for integration scope)
        payload = {
             # "OTA_AirPriceRQ": { ... mapped values ... }
             "message": "Pricing payload mapping requires further analysis of BFM responses"
        }
        
        # Mock block to not block controllers initially
        print("Mock: Calling price_flight", payload)
        return {"status": "Success", "mock_message": "Pricing successful but not fully mapped."}
        
    def create_pnr(self, booking_params: FlightBookingRequest) -> dict:
        """
        Calls Sabre's Create Passenger Name Record API to lock in the booking reservation.
        """
        url = f"{self.base_url}{SabreEndpoints.CREATE_PNR}?mode=create"
        headers = self.get_headers()
        
        person_names = []
        contact_numbers = []
        
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
                
        flight_segments = []
        for segment in booking_params.flight_segments:
            num_passengers = str(len(booking_params.passengers))
            
            departure = segment.get("DepartureDateTime") or segment.get("departure") or ""
            flight_number = str(segment.get("FlightNumber") or segment.get("flight_number") or "")
            res_book_desig_code = segment.get("ResBookDesigCode") or segment.get("cabin_class") or "Y"
            
            dest_loc = segment.get("DestinationLocation", {})
            dest_code = dest_loc.get("LocationCode") if isinstance(dest_loc, dict) else dest_loc or segment.get("destination") or ""
            
            origin_loc = segment.get("OriginLocation", {})
            origin_code = origin_loc.get("LocationCode") if isinstance(origin_loc, dict) else origin_loc or segment.get("origin") or ""
            
            marketing_airline = segment.get("MarketingAirline", {})
            airline_code = marketing_airline.get("Code") if isinstance(marketing_airline, dict) else marketing_airline or segment.get("airline") or ""
            
            flight_segments.append({
                "DepartureDateTime": departure,
                "FlightNumber": flight_number,
                "NumberInParty": num_passengers,
                "ResBookDesigCode": res_book_desig_code,
                "Status": "NN",
                "DestinationLocation": {
                    "LocationCode": dest_code
                },
                "MarketingAirline": {
                    "Code": airline_code,
                    "FlightNumber": flight_number
                },
                "OriginLocation": {
                    "LocationCode": origin_code
                }
            })

        customer_info = {
            "PersonName": person_names
        }
        if contact_numbers:
            customer_info["ContactNumbers"] = {
                "ContactNumber": contact_numbers
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
                "PostProcessing": {
                    "EndTransaction": {
                        "Source": {
                            "ReceivedFrom": "API"
                        }
                    }
                }
            }
        }
        
        print(f"Sending PNR creation request to Sabre: {url}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"PNR creation failed. {str(e)}{error_details}")
        
    def issue_ticket(self, ticketing_params: TicketingRequest) -> dict:
        """
        Calls Sabre's Air Ticket API linking to an existing PNR.
        """
        url = f"{self.base_url}{SabreEndpoints.ISSUE_TICKET}"
        headers = self.get_headers()
        
        payload = {
            "AirTicketRQ": {
                "DesignatePrinter": {
                    "Printers": {
                        "Ticket": {
                            "CountryCode": "US" # dynamic
                        }
                    }
                },
                "Itinerary": {
                    "ID": ticketing_params.pnr
                },
                "Ticketing": [
                     {
                         "PricingQualifiers":{
                              "PriceQuote":[
                                   {
                                        "Record":[
                                             {
                                                  "Number": 1
                                             }
                                        ]
                                   }
                              ]
                         }
                     }
                ]
            }
        }
        
        print("Mock: Calling issue_ticket", payload)
        return {"status": "Success", "message": f"Tickets issued successfully for {ticketing_params.pnr}"}

    def get_pnr_details(self, details_params: PNRDetailsRequest) -> dict:
        """
        Calls Sabre's Get Passenger Name Record API to retrieve full details of a booking.
        """
        url = f"{self.base_url}{SabreEndpoints.GET_PNR_DETAILS}" # Note: there are v1/trip/orders and passenger/records/locator
        headers = self.get_headers()
        
        payload = {
            "confirmationId": details_params.pnr
        }
        
        print(f"Mock: Calling get_pnr_details for {details_params.pnr}", payload)
        return {"status": "Success", "pnr": details_params.pnr, "details": "Mocked details string"}

    def cancel_itinerary(self, cancel_params: CancelItineraryRequest) -> dict:
        """
        Calls Sabre's Cancel Itinerary API.
        """
        url = f"{self.base_url}{SabreEndpoints.CANCEL_ITINERARY}"
        headers = self.get_headers()
        
        payload = {
            "confirmationId": cancel_params.pnr,
            "cancelAll": cancel_params.cancel_segments
        }
        
        print(f"Mock: Calling cancel_itinerary for {cancel_params.pnr}", payload)
        return {"status": "Success", "message": f"Itinerary {cancel_params.pnr} cancelled successfully."}

    def void_ticket(self, void_params: VoidTicketRequest) -> dict:
        """
        Calls Sabre's Void Ticket API to cancel an issued ticket (usually within 24 hours).
        """
        url = f"{self.base_url}{SabreEndpoints.VOID_TICKET}"
        headers = self.get_headers()
        
        payload = {
            "VoidTicketRQ": {
                "Ticketing": {
                    "eTicketNumber": void_params.ticket_number
                }
            }
        }
        
        print(f"Mock: Calling void_ticket for ticket {void_params.ticket_number}", payload)
        return {"status": "Success", "message": f"Ticket {void_params.ticket_number} voided successfully."}

    def exchange_ticket(self, exchange_params: ExchangeTicketRequest) -> dict:
        """
        Calls Sabre's Automated Exchanges API.
        """
        url = f"{self.base_url}{SabreEndpoints.EXCHANGE_TICKET}"
        headers = self.get_headers()
        
        payload = {
            "AutomatedExchangesRQ": {
                "pnr": exchange_params.pnr,
                "ticketNumber": exchange_params.original_ticket_number
            }
        }
        
        print(f"Mock: Calling exchange_ticket for {exchange_params.pnr}", payload)
        return {"status": "Success", "message": f"Ticket exchanged successfully."}

    def get_seat_maps(self, seat_params: SeatMapRequest) -> dict:
        """
        Calls Sabre's Seat Map API to retrieve available seats for a flight.
        """
        url = f"{self.base_url}{SabreEndpoints.SEAT_MAP}"
        headers = self.get_headers()
        
        payload = {
            "SeatMapRQ": {
                "Flight": seat_params.flight_segment
            }
        }
        
        print("Mock: Calling get_seat_maps", payload)
        return {"status": "Success", "seats": []}

    def get_baggage_allowance(self, baggage_params: BaggageAllowanceRequest) -> dict:
        """
        Calls Sabre's Baggage Allowance API.
        """
        url = f"{self.base_url}{SabreEndpoints.BAGGAGE_ALLOWANCE}"
        headers = self.get_headers()
        
        payload = {
            "BaggageAllowanceRQ": {
                 "pnr": baggage_params.pnr
            }
        }
        
        print("Mock: Calling get_baggage_allowance", payload)
        return {"status": "Success", "allowance": "1PC"}

    def place_in_queue(self, queue_params: QueueRequest) -> dict:
        """
        Calls Sabre's Queue Place API to manage agent queues.
        """
        url = f"{self.base_url}{SabreEndpoints.QUEUE_PLACE}"
        headers = self.get_headers()
        
        payload = {
            "QueuePlaceRQ": {
                "QueueInfo": {
                    "QueueIdentifier": [
                        {
                            "Number": queue_params.queue_number,
                            "PseudoCityCode": queue_params.pseudo_city_code
                        }
                    ]
                }
            }
        }
        
        print(f"Mock: Placing PNR {queue_params.pnr} on queue {queue_params.queue_number}", payload)
        return {"status": "Success", "message": "PNR placed on queue"}

    def get_fare_rules(self, rules_params: FareRulesRequest) -> dict:
        """
        Calls Sabre's Structure Fare Rules API.
        """
        url = f"{self.base_url}{SabreEndpoints.STRUCTURE_FARE_RULES}"
        headers = self.get_headers()
        
        payload = {
             "StructureFareRulesRQ": {
                  # ... dynamic mappings
             }
        }
        
        print("Mock: Calling get_fare_rules", payload)
        return {"status": "Success", "rules": ["Mock Rule 1", "Mock Rule 2"]}
