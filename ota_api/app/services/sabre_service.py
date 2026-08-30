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
        import datetime
        url = f"{self.base_url}{SabreEndpoints.FLIGHT_CHECK}"
        headers = self.get_headers()
        
        # Extract and format journeys/flights for Flight Check API v1 (Strict Schema)
        flights = []
        for segment in pricing_params.flight_segments:
            # Departure Date and Time separation
            departure = segment.get("DepartureDateTime") or segment.get("departure")
            dep_date = ""
            dep_time = ""
            
            direct_dep_date = segment.get("departure_date") or segment.get("departureDate") or segment.get("date")
            
            if isinstance(departure, dict):
                dep_date = departure.get("date", "")
                dep_time = departure.get("time", "")
            elif isinstance(departure, str) and "T" in departure:
                parts = departure.split("T")
                dep_date = parts[0]
                dep_time = parts[1][:5] # HH:MM
            elif isinstance(departure, str):
                if len(departure) >= 10:
                    dep_date = departure[:10]
                if len(departure) >= 16:
                    dep_time = departure[11:16]
            
            if not dep_date and direct_dep_date:
                dep_date = str(direct_dep_date)[:10]

            # Fallbacks for departure
            if not dep_date:
                dep_date = datetime.date.today().isoformat()
            if not dep_time:
                dep_time = "00:00"
            
            # Arrival Date and Time separation
            arrival = segment.get("ArrivalDateTime") or segment.get("arrival")
            arr_date = ""
            arr_time = ""
            
            direct_arr_date = segment.get("arrival_date") or segment.get("arrivalDate")
            
            if isinstance(arrival, dict):
                arr_date = arrival.get("date", "")
                arr_time = arrival.get("time", "")
            elif isinstance(arrival, str) and "T" in arrival:
                parts = arrival.split("T")
                arr_date = parts[0]
                arr_time = parts[1][:5] # HH:MM
            elif isinstance(arrival, str):
                if len(arrival) >= 10:
                    arr_date = arrival[:10]
                if len(arrival) >= 16:
                    arr_time = arrival[11:16]
                    
            if not arr_date and direct_arr_date:
                arr_date = str(direct_arr_date)[:10]
                
            # Fallbacks for arrival
            if not arr_date:
                arr_date = dep_date
            if not arr_time:
                arr_time = "23:59"
            
            # AtBooking class
            booking_class = segment.get("ResBookDesigCode") or segment.get("bookingClass") or segment.get("bookingCode")
            if not booking_class:
                details = segment.get("details", {})
                booking_class = details.get("bookingClass") or segment.get("bookingCode") or segment.get("cabinClass") or "Y"
            
            # Extract codes
            dest_loc = segment.get("DestinationLocation") or segment.get("destination") or segment.get("arrival")
            dest_code = ""
            if isinstance(dest_loc, dict):
                dest_code = dest_loc.get("LocationCode") or dest_loc.get("code") or dest_loc.get("airport") or ""
            else:
                dest_code = str(dest_loc or "")
                
            origin_loc = segment.get("OriginLocation") or segment.get("origin") or segment.get("departure")
            origin_code = ""
            if isinstance(origin_loc, dict):
                origin_code = origin_loc.get("LocationCode") or origin_loc.get("code") or origin_loc.get("airport") or ""
            else:
                origin_code = str(origin_loc or "")
                
            airline_info = segment.get("MarketingAirline") or segment.get("airline")
            airline_code = ""
            if isinstance(airline_info, dict):
                airline_code = airline_info.get("Code") or airline_info.get("marketing") or airline_info.get("code") or ""
            else:
                airline_code = str(airline_info or "")

            flights.append({
                "departureDate": dep_date,
                "departureTime": dep_time,
                "departureAirportCode": origin_code,
                "arrivalDate": arr_date,
                "arrivalTime": arr_time,
                "arrivalAirportCode": dest_code,
                "marketingAirlineCode": airline_code,
                "marketingFlightNumber": int("".join(c for c in str(segment.get("FlightNumber") or segment.get("flightNumber") or segment.get("flight_number") or "0") if c.isdigit()) or 0),
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
            num_passengers = str(len(booking_params.passengers))
            
            # Extract and format DepartureDateTime properly
            departure = segment.get("DepartureDateTime") or segment.get("departure")
            dep_date = ""
            dep_time = ""
            
            direct_dep_date = segment.get("departure_date") or segment.get("departureDate") or segment.get("date")
            
            if isinstance(departure, dict):
                dep_date = departure.get("date", "")
                dep_time = departure.get("time", "")
            elif isinstance(departure, str) and "T" in departure:
                parts = departure.split("T")
                dep_date = parts[0]
                dep_time = parts[1][:8] # Keep up to HH:MM:SS
            elif isinstance(departure, str):
                if len(departure) >= 10:
                    dep_date = departure[:10]
                if len(departure) >= 16:
                    dep_time = departure[11:]
            
            if not dep_date and direct_dep_date:
                dep_date = str(direct_dep_date)[:10]

            # Fallbacks for departure
            if not dep_date:
                import datetime
                dep_date = datetime.date.today().isoformat()
            if not dep_time:
                dep_time = "00:00:00"
            else:
                # Ensure the time has seconds, e.g. HH:MM -> HH:MM:SS
                dep_time = dep_time.strip()
                main_time = dep_time
                tz_suffix = ""
                if "+" in dep_time:
                    parts = dep_time.split("+")
                    main_time = parts[0]
                    tz_suffix = "+" + parts[1]
                elif "-" in dep_time and len(dep_time.split("-")) > 1 and ":" in dep_time.split("-")[-1]:
                    parts = dep_time.rsplit("-", 1)
                    main_time = parts[0]
                    tz_suffix = "-" + parts[1]
                elif dep_time.endswith("Z"):
                    main_time = dep_time[:-1]
                    tz_suffix = "Z"
                
                main_time = main_time.strip()
                if len(main_time) == 5:
                    main_time = f"{main_time}:00"
                elif len(main_time) == 8:
                    pass
                elif len(main_time) > 8:
                    main_time = main_time[:8]
                dep_time = f"{main_time}{tz_suffix}"
            
            departure_str = f"{dep_date}T{dep_time}"

            flight_number = str(segment.get("FlightNumber") or segment.get("flightNumber") or segment.get("flight_number") or "")
            
            res_book_desig_code = segment.get("ResBookDesigCode") or segment.get("bookingClass") or segment.get("bookingCode") or segment.get("cabinClass") or segment.get("cabin_class")
            if not res_book_desig_code:
                details = segment.get("details", {})
                res_book_desig_code = details.get("bookingClass") or details.get("bookingCode") or "Y"
            
            dest_loc = segment.get("DestinationLocation") or segment.get("destination") or segment.get("arrival")
            dest_code = ""
            if isinstance(dest_loc, dict):
                dest_code = dest_loc.get("LocationCode") or dest_loc.get("code") or dest_loc.get("airport") or ""
            else:
                dest_code = str(dest_loc or "")
                
            origin_loc = segment.get("OriginLocation") or segment.get("origin") or segment.get("departure")
            origin_code = ""
            if isinstance(origin_loc, dict):
                origin_code = origin_loc.get("LocationCode") or origin_loc.get("code") or origin_loc.get("airport") or ""
            else:
                origin_code = str(origin_loc or "")
                
            marketing_airline = segment.get("MarketingAirline") or segment.get("airline")
            airline_code = ""
            if isinstance(marketing_airline, dict):
                airline_code = marketing_airline.get("Code") or marketing_airline.get("marketing") or marketing_airline.get("code") or ""
            else:
                airline_code = str(marketing_airline or "")
            
            flight_segments.append({
                "DepartureDateTime": departure_str,
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

    def reprice_pnr(self, pnr: str, passenger_types: list = None) -> dict:
        """
        Reprices / re-generates the price quote on an existing PNR.
        Used when the original price quote has expired.

        Returns both the raw Sabre response and a parsed `pricing` dict with:
          - total_fare, base_fare, tax_amount, currency, quote_number

        :param pnr:             6-character Sabre Record Locator
        :param passenger_types: list of dicts like [{"Code": "ADT", "Quantity": "1"}]
                                If None, defaults to 1 adult.
        :return: dict with keys: raw_response, pricing, success, message
        """
        url = f"{self.base_url}{SabreEndpoints.CREATE_PNR}?mode=reprice"
        headers = self.get_headers()

        if not passenger_types:
            passenger_types = [{"Code": "ADT", "Quantity": "1"}]

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
                                "PricingQualifiers": {
                                    "PassengerType": passenger_types
                                }
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
                            "ReceivedFrom": f"{SABRE_PCC} REPRICE"
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
        The caller is responsible for ensuring the price quote is fresh
        (call reprice_pnr() first if needed).
        """
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
                                            "Number": ticketing_params.quote_number or 1,
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

        # Validating carrier is already bound to the stored Price Quote (PQ) during CreatePassengerNameRecordRQ.

        print(f"[Issue] Sending Ticketing request to Sabre: {url} | PNR: {ticketing_params.pnr}", flush=True)

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
        
        country = getattr(exchange_params, 'country_code', None) or "BD"
        lniata = SABRE_LNIATA

        payload = {
            "AirTicketRQ": {
                "version": "1.3.0",
                "targetCity": SABRE_PCC,
                "DesignatePrinter": {
                    "Printers": {
                        "AtFlightTicket": {
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
                            "ReceivedFrom": f"{SABRE_PCC} WEB"
                        }
                    }
                }
            }
        }
        
        print(f"[Exchange] Sending AtFlightTicket Exchange request to Sabre: {url} | PNR: {exchange_params.pnr} | Original AtFlightTicket: {exchange_params.original_ticket_number}", flush=True)
        
        try:
            response = requests.post(url, headers=headers, json=payload)
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
        departure_val = get_val(["departure_date", "departureDate", "DepartureDateTime", "departure"])
        departure_date = ""
        if isinstance(departure_val, dict):
            departure_date = departure_val.get("date") or ""
        elif isinstance(departure_val, str):
            if "T" in departure_val:
                departure_date = departure_val.split("T")[0]
            else:
                departure_date = departure_val[:10]
        
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

        # Extract codes robustly
        dest_loc = segment.get("DestinationLocation") or segment.get("destination") or segment.get("arrival")
        dest_code = ""
        if isinstance(dest_loc, dict):
            dest_code = dest_loc.get("LocationCode") or dest_loc.get("code") or dest_loc.get("airport") or ""
        else:
            dest_code = str(dest_loc or "")
            
        origin_loc = segment.get("OriginLocation") or segment.get("origin") or segment.get("departure")
        origin_code = ""
        if isinstance(origin_loc, dict):
            origin_code = origin_loc.get("LocationCode") or origin_loc.get("code") or origin_loc.get("airport") or ""
        else:
            origin_code = str(origin_loc or "")
            
        airline_info = segment.get("MarketingAirline") or segment.get("airline")
        airline_code = ""
        if isinstance(airline_info, dict):
            airline_code = airline_info.get("Code") or airline_info.get("marketing") or airline_info.get("code") or ""
        else:
            airline_code = str(airline_info or "")

        # Handle Date formatting (YYYY-MM-DD)
        departure_val = segment.get("departure_date") or segment.get("departureDate") or segment.get("DepartureDateTime") or segment.get("departure")
        departure_date = ""
        if isinstance(departure_val, dict):
            departure_date = departure_val.get("date") or ""
        elif isinstance(departure_val, str):
            if "T" in departure_val:
                departure_date = departure_val.split("T")[0]
            else:
                departure_date = departure_val[:10]

        booking_class = segment.get("booking_class") or segment.get("bookingClass") or segment.get("bookingCode") or segment.get("ResBookDesigCode") or segment.get("cabinClass") or segment.get("cabin_class") or "Y"
        if isinstance(booking_class, dict):
            booking_class = booking_class.get("code") or "Y"

        flight_number = str(segment.get("flight_number") or segment.get("flightNumber") or segment.get("FlightNumber") or "")

        # Build flight segment for fare rules lookup
        payload = {
            "originDestination": [
                {
                    "departure": {
                        "airportCode": origin_code,
                        "date": departure_date
                    },
                    "arrival": {
                        "airportCode": dest_code
                    }
                }
            ],
            "travelers": [
                {
                    "passengerTypeCode": segment.get("passenger_type") or segment.get("passengerTypeCode") or "ADT"
                }
            ],
            "fareRulesRequest": {
                "fareBasisCode": segment.get("fare_basis_code") or segment.get("fareBasisCode"),
                "marketingAirlineCode": airline_code,
                "flightNumber": flight_number,
                "bookingClass": booking_class,
                "departureDate": departure_date,
                "origin": origin_code,
                "destination": dest_code
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
