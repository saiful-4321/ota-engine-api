import datetime
from typing import Optional, Dict, Any, List, Tuple

from app.services.travelport_auth_service import TravelportBaseService, create_http_session
from app.services.travelport_endpoints import TravelportEndpoints
from app.services.supplier_config_service import SupplierConfig
from app.utils.redis_utils import redis_helper
from app.models.flight_schemas import (
    FlightSearchRequest, FlightPricingRequest, FlightBookingRequest,
    TicketingRequest, PNRDetailsRequest, CancelItineraryRequest,
    VoidTicketRequest, ExchangeTicketRequest, ExchangeQuoteRequest,
    RefundQuoteRequest, RefundTicketRequest, SeatMapRequest,
    BaggageAllowanceRequest, QueueRequest, FareRulesRequest
)
from app.utils.flight.errors import SupplierError
# The Sabre segment parser understands every segment shape the frontend sends back
# (search response, snake_case, PascalCase); reuse it for exchange matching and seat maps.
from app.services.sabre_service import _parse_sabre_segment as _parse_any_segment


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
            raise SupplierError(f"Flight search failed. {str(e)}")


    def price_flight(self, pricing_params: FlightPricingRequest) -> dict:
        offer_id = pricing_params.offer_id
        if not offer_id and pricing_params.flight_segments:
            seg = pricing_params.flight_segments[0]
            offer_id = seg.get("offer_id") or seg.get("offerId") or seg.get("id")

        offer = _split_offer_id(offer_id)
        custom_headers = {"TraceId": offer["trace_id"]} if offer["trace_id"] else {}
        cpo_id = offer["catalog_id"]
        prod_ref = offer["product_ids"] or "p0"
        val_carrier = offer["validating_carrier"]
        offer_id = offer["offering_ids"]

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

        raw_offer_ids = [o.strip() for o in (offer_id or "o0").split(",") if o.strip()]
        raw_prod_refs = [p.strip() for p in (prod_ref or "p0").split(",") if p.strip()]

        selections = []
        for i, oid in enumerate(raw_offer_ids):
            pref = raw_prod_refs[i] if i < len(raw_prod_refs) else (raw_prod_refs[0] if raw_prod_refs else "p0")
            selections.append({
                "CatalogProductOfferingIdentifier": {
                    "Identifier": {
                        "value": oid
                    }
                },
                "ProductIdentifier": [
                    {
                        "Identifier": {
                            "value": pref
                        }
                    }
                ]
            })

        build_request: Dict[str, Any] = {
            "@type": "BuildFromCatalogProductOfferingsRequestAir",
            "CatalogProductOfferingSelection": selections
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
            raise SupplierError(f"Flight pricing revalidation failed. {str(e)}")


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
            raise SupplierError(
                f"Failed to create Travelport Workbench"
                + (f": {gds_msgs}" if gds_msgs else "")
            )

        settings = self.config.settings or {}
        lead = booking_params.passengers[0]
        lead_phone = lead.phone or str(settings.get("agency_phone") or "")
        lead_email = lead.email or settings.get("agency_email")

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
                dob = pax.date_of_birth
                t_node = {
                    "@type": "Traveler",
                    "id": f"trav_{idx+1}",
                    "passengerTypeCode": {"CNN": "CHD"}.get(pax.passenger_type, pax.passenger_type or "ADT"),
                    "gender": gender,
                    "birthDate": dob,
                    "PersonName": {
                        "@type": "PersonNameDetail",
                        "Given": pax.first_name,
                        "Surname": pax.last_name
                    }
                }
                # Contact: passenger → lead passenger → agency (settings). Never invent contact data:
                # airlines use it for schedule-change notifications.
                raw_phone = pax.phone or lead_phone
                digits_phone = "".join(c for c in raw_phone if c.isdigit() or c == "+")
                if digits_phone:
                    c_code, num = "880", digits_phone
                    if digits_phone.startswith("+880"):
                        num = digits_phone[4:]
                    elif digits_phone.startswith("880"):
                        num = digits_phone[3:]
                    elif digits_phone.startswith("+"):
                        c_code, num = digits_phone[1:4], digits_phone[4:]
                    # Drop the national trunk prefix: 880 + 01600000001 must be sent as 880 1600000001
                    num = num.lstrip("0") or num
                    t_node["Telephone"] = [{
                        "@type": "Telephone",
                        "countryAccessCode": c_code,
                        "phoneNumber": num,
                        "id": f"phone_{idx+1}",
                        "cityCode": self.config.station_code,
                        "role": "Home"
                    }]

                email_val = pax.email or lead_email
                if email_val:
                    t_node["Email"] = [{"value": email_val}]

                if pax.document_number:
                    t_node["TravelDocument"] = [{
                        "@type": "TravelDocumentDetail",
                        "docNumber": pax.document_number,
                        "docType": "Passport",
                        "expireDate": pax.document_expiry,
                        "issueCountry": (pax.document_issue_country or pax.nationality or self.config.country_code).upper(),
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
                            "countryAccessCode": str(settings.get("agency_phone_country_code") or "880"),
                            "areaCityCode": str(settings.get("agency_phone_area_code") or "2"),
                            "phoneNumber": str(settings.get("agency_phone_number") or "9887766")
                        }
                    ]
                }
            }
        }

        raw_offer_ids = [o.strip() for o in (offer_id or "o0").split(",") if o.strip()]
        raw_prod_refs = [p.strip() for p in (prod_ref or "p0").split(",") if p.strip()]

        selections = []
        for i, oid in enumerate(raw_offer_ids):
            pref = raw_prod_refs[i] if i < len(raw_prod_refs) else (raw_prod_refs[0] if raw_prod_refs else "p0")
            selections.append({
                "CatalogProductOfferingIdentifier": {
                    "Identifier": {
                        "value": oid
                    }
                },
                "ProductIdentifier": [
                    {
                        "Identifier": {
                            "value": pref
                        }
                    }
                ]
            })

        build_req: Dict[str, Any] = {
            "@type": "BuildFromCatalogProductOfferingsRequestAir",
            "CatalogProductOfferingSelection": selections
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
                        raise SupplierError(f"PNR creation failed (GDS error, retry): {err_str}")

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
                        raise SupplierError(str(retry_err))

                raise commit_err

        except Exception as e:
            raise SupplierError(f"PNR creation failed. {str(e)}")


    def extract_booked_price(self, response: dict) -> dict:
        """Fare on the committed reservation's air offers."""
        reservation = (response or {}).get("ReservationResponse", {}).get("Reservation", {}) or {}
        total = base = tax = 0.0
        currency = None
        for offer in _as_list(reservation.get("Offer")):
            price = (offer or {}).get("Price") or {}
            total += _amount(price) or 0.0
            base += float(price.get("Base") or 0)
            tax += float(price.get("TotalTaxes") or 0)
            currency = currency or _currency(price)
        return {"total_fare": round(total, 2), "base_fare": round(base, 2), "tax_amount": round(tax, 2), "currency": currency}

    # ── Post-commit workbench helpers ────────────────────────────────────────

    def _open_post_commit_workbench(self, locator: str) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
        """Opens a workbench on an existing reservation. Returns (workbench_id, session headers, reservation)."""
        res = self.request("POST", TravelportEndpoints.WORKBENCH_FROM_LOCATOR, params={"Locator": locator})
        headers: Dict[str, str] = {}
        sid = _header(res, "TravelportPlusSessionIdentifier")
        if sid:
            headers["TravelportPlusSessionIdentifier"] = sid

        reservation = res.get("ReservationResponse", {}).get("Reservation", {}) or {}
        wb_id = reservation.get("Identifier", {}).get("value")
        if not wb_id:
            raise SupplierError(f"Could not open a Travelport workbench for {locator}")

        if not reservation.get("Offer"):
            retrieved = self.request("GET", TravelportEndpoints.RESERVATION_GET.format(id=locator))
            reservation = {**retrieved.get("ReservationResponse", {}).get("Reservation", {}), "Identifier": {"value": wb_id}}
        return wb_id, headers, reservation

    def _discard_workbench(self, wb_id: Optional[str], headers: Optional[Dict[str, str]] = None) -> None:
        if not wb_id:
            return
        try:
            self.request("DELETE", TravelportEndpoints.WORKBENCH_IGNORE.format(id=wb_id), custom_headers=headers)
        except Exception:
            pass  # best effort — Travelport also expires idle workbenches

    def release_quote(self, quote: Optional[Dict[str, Any]]) -> None:
        ctx = (quote or {}).get("context") or {}
        self._discard_workbench(ctx.get("workbench_id"), ctx.get("headers"))

    def _add_cash_payment(self, wb_id: str, headers: Dict[str, str], offers: List[Dict[str, Any]],
                          amount: float, currency: str) -> None:
        """Adds a cash FOP to the workbench and applies it to the given offers (Add FOP + Add Payment)."""
        fop_ref = "formOfPayment_1"
        self.request(
            "POST", TravelportEndpoints.WORKBENCH_FOP.format(id=wb_id),
            json={"FormOfPaymentCash": {"id": fop_ref, "FormOfPaymentRef": fop_ref}},
            custom_headers=headers,
        )
        payment = {
            "Payment": {
                "id": "payment_1",
                "Amount": {"code": currency, "minorUnit": 2, "currencySource": "Charged", "value": f"{amount:.2f}"},
                "FormOfPaymentIdentifier": {"id": fop_ref, "FormOfPaymentRef": fop_ref},
                "OfferIdentifier": [
                    {
                        "id": o.get("id") or f"offer_{i+1}",
                        "offerRef": o.get("id") or f"offer_{i+1}",
                        "Identifier": {"authority": "Travelport", "value": (o.get("Identifier") or {}).get("value")},
                    }
                    for i, o in enumerate(offers)
                ],
            }
        }
        self.request("POST", TravelportEndpoints.WORKBENCH_PAYMENT.format(id=wb_id), json=payment, custom_headers=headers)

    def _list_tickets(self, locator: str) -> List[Dict[str, Any]]:
        try:
            res = self.request("GET", TravelportEndpoints.RESERVATION_RECEIPTS.format(locator=locator))
        except Exception:
            return []
        tickets = []
        for doc in _find_all(res, "Document"):
            for d in _as_list(doc):
                if not isinstance(d, dict):
                    continue
                num = d.get("Number") or d.get("number") or (d.get("DocumentNumber") or {}).get("value")
                if num:
                    tickets.append({"TicketNumber": str(num), "PassengerName": d.get("name") or ""})
        return tickets

    # ── Ticketing ────────────────────────────────────────────────────────────

    def reprice_pnr(self, pnr: str, passenger_types: list = None, validating_carrier: str = None) -> dict:
        """
        Returns the fare stored on the reservation's air offers. Travelport re-validates the fare
        at commit time (errorWhenOfferPriceChangesInd), so issuance can never silently charge more.
        """
        quote = self.quote_issue(pnr)
        self.release_quote(quote)
        return {
            "success": True,
            "message": "Stored fare retrieved; Travelport re-validates the fare at ticketing.",
            "pricing": {
                "total_fare": quote["amount"], "base_fare": quote["base"], "tax_amount": quote["tax"],
                "currency": quote["currency"], "quote_number": None,
            },
        }

    def quote_issue(self, pnr: str, passenger_types: list = None, validating_carrier: str = None) -> dict:
        """Opens a ticketing workbench and returns the stored fare. Keep the quote for issue_ticket()."""
        wb_id, headers, reservation = self._open_post_commit_workbench(pnr)
        offers = [o for o in _as_list(reservation.get("Offer")) if isinstance(o, dict)]
        if not offers:
            self._discard_workbench(wb_id, headers)
            raise SupplierError(f"Reservation {pnr} has no priced air offer to ticket")

        total = base = tax = 0.0
        currency = None
        for o in offers:
            price = o.get("Price") or {}
            total += _amount(price) or 0.0
            base += float(price.get("Base") or 0)
            tax += float(price.get("TotalTaxes") or 0)
            currency = currency or _currency(price)

        return {
            "amount": round(total, 2), "base": round(base, 2), "tax": round(tax, 2), "currency": currency,
            "context": {"workbench_id": wb_id, "headers": headers, "offers": offers},
        }

    def issue_ticket(self, ticketing_params: TicketingRequest, quote: dict) -> dict:
        """
        Issues tickets on a workbench opened by quote_issue(): add cash FOP + payment for the fare,
        then commit with Issuance=Ticket. Travelport rejects the commit if the offer price changed.
        """
        ctx = quote["context"]
        wb_id, headers = ctx["workbench_id"], ctx["headers"]
        try:
            self._add_cash_payment(wb_id, headers, ctx["offers"], quote["amount"], quote["currency"])
            commit = self.request(
                "POST", TravelportEndpoints.WORKBENCH_COMMIT.format(id=wb_id),
                params={"Issuance": "Ticket"},
                # @type is required — without it Travelport rejects the body (1586 INVALID INPUT FORMAT)
                json={"@type": "ReservationQueryCommitReservation", "errorWhenOfferPriceChangesInd": True},
                custom_headers=headers,
            )
        except Exception as exc:
            self._discard_workbench(wb_id, headers)
            if "PLATING CARRIER" in str(exc).upper():
                carrier = next((v for v in _find_all(ctx["offers"], "ValidatingAirline") if isinstance(v, str)), "?")
                env = "pre-production" if ".pp." in (self.base_url or "") else "production"
                raise SupplierError(
                    f"Ticketing refused by Galileo: UNAUTHORISED/INVALID PLATING CARRIER CODE for validating "
                    f"carrier {carrier} on PCC {self.config.pcc or '?'} ({env} Travelport). Nothing was issued. "
                    f"This is decided by the Travelport account set-up (plating agreements available to this "
                    f"PCC/credentials in this environment), not by the request — confirm with Travelport. "
                    f"| Details: {exc}"
                ) from exc
            raise

        tickets = self._list_tickets(ticketing_params.pnr)
        if not tickets:
            raise SupplierError(
                f"Travelport commit succeeded for {ticketing_params.pnr} but no ticket numbers were returned "
                f"— check the reservation before retrying."
            )
        return {"status": "Success", "pnr": ticketing_params.pnr, "TicketDetails": tickets, "raw_response": commit}

    def get_pnr_details(self, details_params: PNRDetailsRequest) -> dict:
        return self.request("GET", TravelportEndpoints.RESERVATION_GET.format(id=details_params.pnr))

    def cancel_itinerary(self, cancel_params: CancelItineraryRequest) -> dict:
        """GDS reservation cancel: POST receipts on the locator (no payload)."""
        res = self.request("POST", TravelportEndpoints.RESERVATION_RECEIPTS.format(locator=cancel_params.pnr))
        return {"status": "success", "pnr": cancel_params.pnr, "raw_response": res}

    def void_ticket(self, void_params: VoidTicketRequest) -> dict:
        payload = {
            "DocumentVoidRequest": {
                "DocumentVoidRequest": {
                    "documentNumber": [void_params.ticket_number]
                }
            }
        }
        return self.request("POST", TravelportEndpoints.VOID_BATCH, json=payload)

    # ── Exchange (GDS) ───────────────────────────────────────────────────────

    def quote_exchange(self, params: ExchangeQuoteRequest, passenger_types: Optional[list] = None,
                       keep_open: bool = False) -> dict:
        """
        Prices an exchange to the requested flights via Exchange Search on a post-commit workbench.
        The workbench is discarded unless keep_open=True (used by exchange_ticket's live re-quote).
        Returns: amount (to collect), currency, breakdown, context.
        """
        wb_id, headers, reservation = self._open_post_commit_workbench(params.pnr)
        try:
            offers = [o for o in _as_list(reservation.get("Offer")) if isinstance(o, dict)]
            if not offers:
                raise SupplierError(f"Reservation {params.pnr} has no air offer to exchange")
            offer = offers[0]
            product_ids = [{"id": p.get("id")} for p in _as_list(offer.get("Product")) if isinstance(p, dict) and p.get("id")]
            travelers = [t for t in _as_list(reservation.get("Traveler")) if isinstance(t, dict)]

            payload = {
                "CatalogOfferingsQueryAirChange": {
                    "CatalogOfferingsAirChangeRequest": {
                        "@type": "CatalogOfferingsAirChangeRequestReservation",
                        "BuildFromReservationWorkbench": {
                            "ReservationIdentifier": {"Identifier": {"authority": "Travelport", "value": wb_id}},
                            "OfferIdentifier": {"id": offer.get("id")},
                            "ProductIdentifier": product_ids,
                        },
                        "PassengerCriteria": [
                            {
                                "@type": "PassengerCriteria",
                                "number": 1,
                                "passengerTypeCode": t.get("passengerTypeCode") or "ADT",
                                "TravelerIdentifierRef": {"id": t.get("id")},
                            }
                            for t in travelers
                        ],
                        "SearchCriteriaFlight": _search_criteria_from_segments(params.new_flight_segments),
                    }
                }
            }
            res = self.request("POST", TravelportEndpoints.EXCHANGE_SEARCH, json=payload, custom_headers=headers)
            match = _match_exchange_offering(res, params.new_flight_segments)
            if not match:
                raise SupplierError("The requested flights are not available as an exchange option for this ticket")

            quote = {
                "amount": match["amount_due"],
                "currency": match["currency"],
                "breakdown": match["breakdown"],
                "context": {
                    "workbench_id": wb_id,
                    "headers": headers,
                    "catalog_offerings_identifier": match["catalog_offerings_identifier"],
                    "catalog_offering_id": match["catalog_offering_id"],
                },
            }
        except Exception:
            self._discard_workbench(wb_id, headers)
            raise
        if not keep_open:
            self._discard_workbench(wb_id, headers)
            quote["context"] = {k: v for k, v in quote["context"].items() if k not in ("workbench_id", "headers")}
        return quote

    def exchange_ticket(self, params: ExchangeTicketRequest, quote: dict) -> dict:
        """
        Commits an exchange on the workbench left open by quote_exchange(keep_open=True):
        add offer → cash FOP + payment of the add-collect → commit with payLaterInd=false (reissue).
        """
        ctx = quote["context"]
        wb_id, headers = ctx["workbench_id"], ctx["headers"]
        try:
            cid = ctx["catalog_offerings_identifier"]
            offer_res = self.request(
                "POST", TravelportEndpoints.EXCHANGE_ADD_OFFER.format(id=wb_id),
                json={
                    "OfferQueryBuildFromCatalogOfferings": {
                        "BuildFromCatalogOfferingsRequest": {
                            "@type": "BuildFromCatalogOfferingsRequestAir",
                            "CatalogOfferingsIdentifier": {"Identifier": {"value": cid, "authority": "Travelport"}},
                            "CatalogOfferingIdentifier": {
                                "Identifier": {"value": ctx["catalog_offering_id"], "authority": "Travelport"}
                            },
                        }
                    }
                },
                custom_headers=headers,
            )
            new_offers = [o for o in _find_all(offer_res, "Offer") for o in _as_list(o) if isinstance(o, dict)]
            if not new_offers:
                raise SupplierError("Travelport did not return the exchanged offer")
            self._add_cash_payment(wb_id, headers, new_offers[:1], quote["amount"], quote["currency"])
            commit = self.request(
                "POST", TravelportEndpoints.WORKBENCH_COMMIT.format(id=wb_id),
                params={"payLaterInd": "false"},
                # @type is required — without it Travelport rejects the body (1586 INVALID INPUT FORMAT)
                json={"@type": "ReservationQueryCommitReservation", "errorWhenOfferPriceChangesInd": True},
                custom_headers=headers,
            )
        except Exception:
            self._discard_workbench(wb_id, headers)
            raise

        return {
            "status": "Success",
            "pnr": params.pnr,
            "original_ticket_number": params.original_ticket_number,
            "TicketDetails": self._list_tickets(params.pnr),
            "amount_collected": quote["amount"],
            "currency": quote["currency"],
            "raw_response": commit,
        }

    # ── Refund (GDS) ─────────────────────────────────────────────────────────

    def quote_refund(self, params: RefundQuoteRequest) -> dict:
        """Prices a refund with Document Refund Quote (read-only)."""
        payload = {
            "@type": "OfferQueryDocumentRefundQuote",
            "DocumentRefundQuote": [
                {
                    "@type": "DocumentRefundQuote",
                    "DocumentNumber": [
                        {"value": t, "documentType": "Ticket", "id": f"doc_{i+1}"}
                        for i, t in enumerate(params.ticket_numbers)
                    ],
                }
            ],
        }
        res = self.request("POST", TravelportEndpoints.DOCUMENT_REFUND_QUOTE, json=payload)

        amount = penalty = 0.0
        currency = None
        for node in _find_all(res, "ModifyPrice"):
            for n in _as_list(node):
                amount += _amount(n) or 0.0
                currency = currency or _currency(n)
        for node in _find_all(res, "SupplierRetainedPrice"):
            for n in _as_list(node):
                penalty += _amount(n) or 0.0

        offer_list_id = next((v for v in _find_all(res, "OfferListIdentifier") if v), None)
        if isinstance(offer_list_id, dict):
            offer_list_id = offer_list_id.get("value")
        if not offer_list_id:
            ident = res.get("OfferListResponse", {}).get("Identifier", {})
            offer_list_id = ident.get("value") if isinstance(ident, dict) else None
        offers = [
            o for node in _find_all(res, "Offer") for o in _as_list(node)
            if isinstance(o, dict) and (o.get("Identifier") or {}).get("value")
        ]

        return {
            "refundable": bool(offer_list_id and offers and currency),
            "amount": round(amount, 2),
            "penalty": round(penalty, 2),
            "currency": currency,
            "tickets": list(params.ticket_numbers),
            "context": {"offer_list_id": offer_list_id, "offers": offers},
            "raw_response": res,
        }

    def refund_ticket(self, params: RefundTicketRequest, quote: dict) -> dict:
        """Commits the refund priced by a fresh quote_refund() (controller runs the price guard first)."""
        ctx = quote["context"]
        selection: Dict[str, Any] = {
            "@type": "BuildFromOfferList",
            "OfferListIdentifier": ctx["offer_list_id"],
            "OfferIdentifier": [
                {
                    "id": o.get("id") or f"offer_{i+1}",
                    "offerRef": o.get("id") or f"offer_{i+1}",
                    "Identifier": {"value": o["Identifier"]["value"], "authority": "Travelport"},
                }
                for i, o in enumerate(ctx["offers"])
            ],
        }
        if params.waiver_code:
            selection["WaiverCode"] = params.waiver_code
        res = self.request(
            "POST", TravelportEndpoints.DOCUMENT_REFUND_COMMIT,
            json={"@type": "ReceiptQueryDocumentRefundFromOfferList", "BuildFromOfferList": [selection]},
        )
        status = str(res.get("ReceiptListResponse", {}).get("reservationStatus") or "").lower()
        if status in ("fail", "failed"):
            raise SupplierError(f"Travelport refund failed for {params.pnr} | Details: {res}")
        return {"status": "Success", "pnr": params.pnr, "refund_status": status or "success", "raw_response": res}

    # ── Ancillaries ──────────────────────────────────────────────────────────

    def get_seat_maps(self, seat_params: SeatMapRequest) -> dict:
        """Standalone seat map (GDS content): built from the flight details alone, no search session needed."""
        p = _parse_any_segment(seat_params.flight_segment)
        flight = {
            "@type": "SpecificFlightCriteria",
            "carrier": p["marketing_airline"],
            "flightNumber": p["flight_number_str"],
            "departureDate": p["departure_date"],
            "departureTime": _with_seconds(p["departure_time"]),
            "arrivalDate": p["arrival_date"],
            "arrivalTime": _with_seconds(p["arrival_time"]),
            "from": p["origin"],
            "to": p["destination"],
            "cabin": _map_cabin_class(seat_params.flight_segment.get("cabin") or seat_params.flight_segment.get("cabinClass")),
            "classOfService": p["booking_class"],
            "segmentSequence": 1,
        }
        payload = {
            "CatalogOfferingsQuerySeatAvailability": {
                "SeatAvailabilityOfferings": {
                    "@type": "SeatAvailabilityOfferingsBuildFromProducts",
                    "ProductCriteriaAir": {"@type": "ProductCriteriaAir", "sequence": 1, "SpecificFlightCriteria": [flight]},
                }
            }
        }
        return self.request("POST", TravelportEndpoints.SEAT_AVAILABILITY, json=payload)

    def get_baggage_allowance(self, baggage_params: BaggageAllowanceRequest) -> dict:
        """The reservation carries the allowance (Offer → TermsAndConditionsFull → BaggageAllowance)."""
        return self.get_pnr_details(PNRDetailsRequest(pnr=baggage_params.pnr))

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
        return self.request("POST", TravelportEndpoints.QUEUE_PLACE, json=payload)

    def get_fare_rules(self, rules_params: FareRulesRequest) -> dict:
        """
        Structured change / refund rules — of the booked fare when `pnr` is given, otherwise of the
        search offer. Returns {"structured": ..., "text": ... | None}; `text` (the airline's rule
        text per category) is fetched only when `include_text` is set.
        """
        if rules_params.pnr:
            endpoint, params, headers = (TravelportEndpoints.FARE_RULES_FROM_RESERVATION,
                                         {"reservationIdentifier": rules_params.pnr}, None)
        else:
            endpoint, params, headers = self._fare_rules_offer_query(rules_params.search_offer_id)

        def fetch(rule_type: str) -> dict:
            return self.request("GET", endpoint, params={**params, "fareRuleType": rule_type}, custom_headers=headers)

        return {"structured": fetch("Structured"), "text": fetch("ShortText") if rules_params.include_text else None}

    @staticmethod
    def _fare_rules_offer_query(offer_id: Optional[str]) -> Tuple[str, Dict[str, str], Optional[Dict[str, str]]]:
        offer = _split_offer_id(offer_id)
        if not (offer["offering_ids"] and offer["catalog_id"] and offer["product_ids"]):
            raise ValueError("'offer_id' must be the offer id returned by /search (it carries the catalog and product ids)")
        params = {
            "catalogProductOfferingsIdentifier": offer["catalog_id"],
            # One fare per call: the first offering / product (outbound for round trips).
            "catalogProductOfferingID": offer["offering_ids"].split(",")[0],
            "productIDs": offer["product_ids"].split(",")[0],
        }
        headers = {"TraceId": offer["trace_id"]} if offer["trace_id"] else None
        return TravelportEndpoints.FARE_RULES_FROM_SEARCH, params, headers


# ── Module helpers ────────────────────────────────────────────────────────────

def _split_offer_id(offer_id: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Search packs everything Travelport needs to find an offer again into one `id`:
        "<offering ids, comma separated>@@<trace id>@@<catalog id>@@<product ids>@@<validating carrier>"
    A plain id without '@@' is just the offering id.
    """
    parts = (offer_id or "").split("@@")

    def part(index: int) -> Optional[str]:
        return parts[index] if len(parts) > index and parts[index] else None

    return {"offering_ids": part(0), "trace_id": part(1), "catalog_id": part(2),
            "product_ids": part(3), "validating_carrier": part(4)}


def _with_seconds(time_value: Optional[str]) -> Optional[str]:
    """'17:10' → '17:10:00' (Travelport wants full times)."""
    return f"{time_value}:00" if time_value and len(time_value) == 5 else time_value


def _as_list(val: Any) -> list:
    if val is None:
        return []
    return val if isinstance(val, list) else [val]


def _find_all(obj: Any, key: str) -> list:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            found.extend(_find_all(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_all(item, key))
    return found


def _header(res: Dict[str, Any], name: str) -> Optional[str]:
    target = name.lower()
    for k, v in (res.get("_headers") or {}).items():
        if k.lower() == target:
            return v
    return None


def _amount(price: Any) -> Optional[float]:
    if not isinstance(price, dict):
        return None
    for key in ("TotalPrice", "Total", "totalPrice"):
        if price.get(key) not in (None, ""):
            try:
                return float(price[key])
            except (TypeError, ValueError):
                return None
    return None


def _currency(price: Any) -> Optional[str]:
    if not isinstance(price, dict):
        return None
    cc = price.get("CurrencyCode")
    if isinstance(cc, dict):
        return cc.get("value")
    return cc or price.get("code")


def _search_criteria_from_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Groups the requested segments into origin/destination legs (a connection continues a leg)."""
    parsed = [_parse_any_segment(s) for s in segments]
    legs: List[Dict[str, Any]] = []
    for p in parsed:
        if legs and legs[-1]["To"]["value"] == p["origin"] and p["departure_date"] <= _next_day(legs[-1]["_last_arr"]):
            legs[-1]["To"]["value"] = p["destination"]
            legs[-1]["_last_arr"] = p["arrival_date"]
            continue
        legs.append({
            "@type": "SearchCriteriaFlight",
            "departureDate": p["departure_date"],
            "From": {"value": p["origin"]},
            "To": {"value": p["destination"]},
            "_last_arr": p["arrival_date"],
        })
    for leg in legs:
        leg.pop("_last_arr", None)
    return legs


def _next_day(date_str: str) -> str:
    try:
        return (datetime.date.fromisoformat(date_str) + datetime.timedelta(days=1)).isoformat()
    except Exception:
        return date_str


def _match_exchange_offering(res: Dict[str, Any], segments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Finds the exchange CatalogOffering whose flights are exactly the requested ones and returns its
    identifiers and amount due (AdditionalCollectionPrice, else a positive ModifyPrice, plus fees).
    """
    wanted = set()
    for s in segments:
        p = _parse_any_segment(s)
        wanted.add((p["marketing_airline"], str(p["flight_number_int"] or ""), p["departure_date"]))

    flights = {}
    for ref in _find_all(res, "ReferenceList"):
        for r in _as_list(ref):
            if isinstance(r, dict) and r.get("@type") == "ReferenceListFlight":
                for f in _as_list(r.get("Flight")):
                    dep = f.get("Departure") or {}
                    num = "".join(c for c in str(f.get("number") or "") if c.isdigit()).lstrip("0")
                    flights[f.get("id")] = (str(f.get("carrier") or "").upper(), num, str(dep.get("date") or "")[:10])

    root = next(iter(v for k, v in res.items() if isinstance(v, dict) and "CatalogOfferings" in v), {})
    catalog = root.get("CatalogOfferings") or {}
    cid = (catalog.get("Identifier") or {}).get("value")

    for off in _as_list(catalog.get("CatalogOffering")):
        refs = {r for r in _find_all(off, "flightRefs") for r in _as_list(r)}
        refs |= {r for r in _find_all(off, "FlightRef") for r in _as_list(r) if isinstance(r, str)}
        if {flights[r] for r in refs if r in flights} != wanted:
            continue

        modify = next(iter(_as_list(next(iter(_find_all(off, "ModifyPrice")), None))), None)
        addl = next(iter(_as_list(next(iter(_find_all(off, "AdditionalCollectionPrice")), None))), None)
        due = _amount(addl)
        if due is None:
            due = max(_amount(modify) or 0.0, 0.0)
        currency = _currency(addl) or _currency(modify) or _currency(next(iter(_find_all(off, "Price")), None))
        return {
            "catalog_offerings_identifier": cid,
            "catalog_offering_id": off.get("id"),
            "amount_due": round(due, 2),
            "currency": currency,
            "breakdown": {
                "modify_price": modify,
                "additional_collection_price": addl,
                "residual_price": next(iter(_find_all(off, "ResidualPrice")), None),
                "supplier_retained_price": next(iter(_find_all(off, "SupplierRetainedPrice")), None),
            },
        }
    return None
