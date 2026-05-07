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
from config import SABRE_PCC, SABRE_LNIATA

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
        Calls Sabre's Flight Check API to revalidate price and availability.
        """
        url = f"{self.base_url}{SabreEndpoints.FLIGHT_CHECK}"
        headers = self.get_headers()
        
        # Extract and format journeys/flights for Flight Check API v1 (Strict Schema)
        flights = []
        for segment in pricing_params.flight_segments:
            # Departure Date and Time separation
            departure = segment.get("DepartureDateTime") or segment.get("departure")
            dep_date = ""
            dep_time = ""
            
            if isinstance(departure, dict):
                dep_date = departure.get("date", "")
                dep_time = departure.get("time", "")
            elif isinstance(departure, str) and "T" in departure:
                parts = departure.split("T")
                dep_date = parts[0]
                dep_time = parts[1][:5] # HH:MM
            
            # Arrival Date and Time separation
            arrival = segment.get("ArrivalDateTime") or segment.get("arrival")
            arr_date = ""
            arr_time = ""
            
            if isinstance(arrival, dict):
                arr_date = arrival.get("date", "")
                arr_time = arrival.get("time", "")
            elif isinstance(arrival, str) and "T" in arrival:
                parts = arrival.split("T")
                arr_date = parts[0]
                arr_time = parts[1][:5] # HH:MM
            elif not arrival:
                # If arrival is missing, we use departure as a fallback for the date
                arr_date = dep_date
                arr_time = "23:59" # Fallback time
            
            # Booking class
            booking_class = segment.get("ResBookDesigCode") or segment.get("bookingClass")
            if not booking_class:
                details = segment.get("details", {})
                booking_class = details.get("bookingClass") or segment.get("cabinClass") or "Y"
            
            # Extract codes
            dest_loc = segment.get("DestinationLocation") or segment.get("destination")
            dest_code = dest_loc.get("LocationCode") or dest_loc.get("code") if isinstance(dest_loc, dict) else str(dest_loc or "")
                
            origin_loc = segment.get("OriginLocation") or segment.get("origin")
            origin_code = origin_loc.get("LocationCode") or origin_loc.get("code") if isinstance(origin_loc, dict) else str(origin_loc or "")
                
            airline_info = segment.get("MarketingAirline") or segment.get("airline")
            airline_code = airline_info.get("Code") or airline_info.get("marketing") or airline_info.get("code") if isinstance(airline_info, dict) else str(airline_info or "")

            flights.append({
                "departureDate": dep_date,
                "departureTime": dep_time,
                "departureAirportCode": origin_code,
                "arrivalDate": arr_date,
                "arrivalTime": arr_time,
                "arrivalAirportCode": dest_code,
                "marketingAirlineCode": airline_code,
                "marketingFlightNumber": int(segment.get("FlightNumber") or segment.get("flightNumber") or 0),
                "bookingClass": booking_class
            })

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
        
        print(f"Sending Flight Check request to Sabre: {url}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"Flight pricing revalidation failed. {str(e)}{error_details}")
        
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
            
            dest_loc = segment.get("DestinationLocation")
            if isinstance(dest_loc, dict):
                dest_code = dest_loc.get("LocationCode")
            else:
                dest_code = dest_loc
            dest_code = dest_code or segment.get("destination") or ""
            
            origin_loc = segment.get("OriginLocation")
            if isinstance(origin_loc, dict):
                origin_code = origin_loc.get("LocationCode")
            else:
                origin_code = origin_loc
            origin_code = origin_code or segment.get("origin") or ""
            
            marketing_airline = segment.get("MarketingAirline")
            if isinstance(marketing_airline, dict):
                airline_code = marketing_airline.get("Code")
            else:
                airline_code = marketing_airline
            airline_code = airline_code or segment.get("airline") or ""
            
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
                            "OptionalQualifiers": {
                                "PricingQualifiers": {
                                    "PassengerType": pricing_pax_types
                                }
                            }
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
        url = f"{self.base_url}{SabreEndpoints.ISSUE_TICKET}"
        headers = self.get_headers()

        lniata = ticketing_params.printer_id or SABRE_LNIATA
        country = ticketing_params.country_code or "BD"

        payload = {
            "AirTicketRQ": {
                "version": "1.3.0",
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
                        "PricingQualifiers": {
                            "PriceQuote": [
                                {
                                    "Record": [
                                        {
                                            "Number": 1,
                                            "Reissue": ticketing_params.reissue or False
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
                            "ReceivedFrom": f"{SABRE_PCC} WEB"
                        }
                    }
                }
            }
        }

        # Optional: validating carrier override
        if ticketing_params.validating_carrier:
            payload["AirTicketRQ"]["Ticketing"][0]["ValidatingCarrier"] = {
                "Code": ticketing_params.validating_carrier
            }

        print(f"Sending Ticketing request to Sabre: {url}")

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
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
        Calls Sabre's Cancel Booking API to cancel an existing PNR/itinerary.
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
        Calls Sabre's Void Ticket API to cancel an issued ticket (usually within 24 hours).
        """
        url = f"{self.base_url}{SabreEndpoints.VOID_TICKET}"
        headers = self.get_headers()
        
        payload = {
            "VoidTicketRQ": {
                "version": "1.0.0",
                "Ticketing": {
                    "eTicketNumber": void_params.ticket_number
                }
            }
        }
        
        print(f"Sending Void Ticket request to Sabre: {url} | Ticket: {void_params.ticket_number}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"Ticket voiding failed. {str(e)}{error_details}")

    def exchange_ticket(self, exchange_params: ExchangeTicketRequest) -> dict:
        """
        Calls Sabre's Automated Exchanges API.
        """
        url = f"{self.base_url}{SabreEndpoints.EXCHANGE_TICKET}"
        headers = self.get_headers()
        
        payload = {
            "ExchangeTicketRQ": {
                "version": "2.0.0",
                "Ticketing": {
                    "eTicketNumber": exchange_params.original_ticket_number
                },
                "Itinerary": {
                    "ID": exchange_params.pnr
                }
            }
        }
        
        print(f"Sending Ticket Exchange request to Sabre: {url} | PNR: {exchange_params.pnr}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_details = f" | Details: {response.text}"
                print(f"Sabre Error Response: {response.text}")
            raise Exception(f"Ticket exchange failed. {str(e)}{error_details}")

    def get_seat_maps(self, seat_params: SeatMapRequest) -> dict:
        """
        Calls Sabre's Seat Map API to retrieve available seats for a flight.
        """
        url = f"{self.base_url}{SabreEndpoints.SEAT_MAP}"
        headers = self.get_headers()
        
        segment = seat_params.flight_segment
        
        def get_val(keys, default=None):
            for k in keys:
                if k in segment:
                    return segment[k]
            return default

        # Extracting specific fields needed for SeatMapRQ
        dest_loc = get_val(["destination", "DestinationLocation", "arrival"])
        dest_code = dest_loc.get("LocationCode") or dest_loc.get("code") if isinstance(dest_loc, dict) else str(dest_loc or "")
        
        origin_loc = get_val(["origin", "OriginLocation", "departure"])
        origin_code = origin_loc.get("LocationCode") or origin_loc.get("code") if isinstance(origin_loc, dict) else str(origin_loc or "")
        
        airline_info = get_val(["airline", "marketingAirline", "MarketingAirline"])
        airline_code = airline_info.get("Code") or airline_info.get("code") if isinstance(airline_info, dict) else str(airline_info or "")

        # Handle Date formatting (YYYY-MM-DD)
        departure_date = get_val(["departure_date", "departureDate", "DepartureDateTime"])
        if isinstance(departure_date, str) and "T" in departure_date:
            departure_date = departure_date.split("T")[0]
        
        payload = {
            "SeatMapRQ": {
                "version": "3.0.0",
                "Flight": {
                    "Destination": dest_code,
                    "Origin": origin_code,
                    "DepartureDate": departure_date,
                    "MarketingAirline": airline_code,
                    "FlightNumber": str(get_val(["flight_number", "flightNumber", "FlightNumber"]) or ""),
                    "ResBookDesigCode": get_val(["booking_class", "bookingClass", "ResBookDesigCode", "cabinClass"]) or "Y"
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

        segment = rules_params.flight_segment

        # Build flight segment for fare rules lookup
        payload = {
            "originDestination": [
                {
                    "departure": {
                        "airportCode": segment.get("origin"),
                        "date": segment.get("departure_date")
                    },
                    "arrival": {
                        "airportCode": segment.get("destination")
                    }
                }
            ],
            "travelers": [
                {
                    "passengerTypeCode": segment.get("passenger_type", "ADT")
                }
            ],
            "fareRulesRequest": {
                "fareBasisCode": segment.get("fare_basis_code"),
                "marketingAirlineCode": segment.get("airline"),
                "flightNumber": segment.get("flight_number"),
                "bookingClass": segment.get("booking_class", "Y"),
                "departureDate": segment.get("departure_date"),
                "origin": segment.get("origin"),
                "destination": segment.get("destination")
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
