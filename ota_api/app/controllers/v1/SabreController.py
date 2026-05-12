from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import datetime

from app.models.sabre_schemas import (
    FlightSearchRequest, FlightPricingRequest, FlightBookingRequest, TicketingRequest,
    PNRDetailsRequest, CancelItineraryRequest, VoidTicketRequest, ExchangeTicketRequest,
    SeatMapRequest, BaggageAllowanceRequest, QueueRequest, FareRulesRequest
)
from app.services.sabre_service import SabreFlightService

# Define a router specifically for Sabre endpoints
router = APIRouter()

from app.helpers.sabre_helper import (
    format_bfm_response, format_pnr_response, format_pnr_details_response, 
    format_ticketing_response, format_pricing_response, format_cancel_response,
    format_fare_rules_response
)

# Dependency to provide the Sabre service
def get_sabre_service():
    return SabreFlightService()

@router.post("/search/flights", summary="Search Flights (Bargain Finder Max)", description="Search cheapest airfares based on Sabre Bargain Finder Max API.")
async def search_flights(request: FlightSearchRequest, service: SabreFlightService = Depends(get_sabre_service)) -> Dict[str, Any]:
     try:
          response = service.search_flights(request)
          formatted_response = format_bfm_response(response)
          return formatted_response
     except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@router.post("/price/flight", summary="Price a particular Itinerary", description="Verifies pricing for a given flight search outcome.")
async def price_flight(request: FlightPricingRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          # Sabre Flight Check (Revalidation) via service
          response = service.price_flight(request)
          formatted_response = format_pricing_response(response)
          return formatted_response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))

@router.post("/book/pnr", summary="Create Record Locator (PNR)", description="Book flights using Sabre passenger name records.")
async def book_flight(request: FlightBookingRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          # PNR creation via service
          response = service.create_pnr(request)
          formatted_response = format_pnr_response(response)
          return formatted_response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))


@router.post("/ticket/issue", summary="Issue Air Tickets", description="Issues standard tickets for an established reservation (PNR).")
async def ticket_issue(request: TicketingRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          # Air ticket endpoint via service
          response = service.issue_ticket(request)
          formatted_response = format_ticketing_response(response)
          return formatted_response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))

@router.post("/pnr/details", summary="Get PNR Details", description="Retrieves the full passenger name record details.")
async def pnr_details(request: PNRDetailsRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          # Get PNR details via service
          response = service.get_pnr_details(request)
          formatted_response = format_pnr_details_response(response)
          return formatted_response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))

@router.post("/pnr/cancel", summary="Cancel Itinerary", description="Cancels an existing itinerary/PNR.")
async def pnr_cancel(request: CancelItineraryRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          response = service.cancel_itinerary(request)
          formatted_response = format_cancel_response(response)
          return formatted_response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))

@router.post("/ticket/void", summary="Void Ticket", description="Voids a previously issued electronic ticket.")
async def ticket_void(request: VoidTicketRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          # Void Ticket via service
          response = service.void_ticket(request)
          return response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))

@router.post("/ticket/exchange", summary="Exchange Ticket (Auto Reissue)", description="Performs an automated exchange of an existing ticket.")
async def ticket_exchange(request: ExchangeTicketRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          # Exchange Ticket via service
         response = service.exchange_ticket(request)
         return response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))

@router.post("/seats/map", summary="Get Seat Map", description="Retrieves available seats for a specific flight segment.")
async def seat_map(request: SeatMapRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          response = service.get_seat_maps(request)
          return response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))

@router.post("/baggage/allowance", summary="Get Baggage Allowance", description="Checks baggage allowance for a PNR.")
async def baggage_allowance(request: BaggageAllowanceRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          response = service.get_baggage_allowance(request)
          return response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))

@router.post("/pnr/queue", summary="Place PNR on Queue", description="Places a PNR on a specific agency queue.")
async def queue_place(request: QueueRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          response = service.place_in_queue(request)
          return response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))

@router.post("/rules/fare", summary="Get Fare Rules", description="Retrieves structured fare rules for flights.")
async def fare_rules(request: FareRulesRequest, service: SabreFlightService = Depends(get_sabre_service)):
     try:
          response = service.get_fare_rules(request)
          formatted_response = format_fare_rules_response(response)
          return formatted_response
     except Exception as e:
          raise HTTPException(status_code=500, detail=str(e))
