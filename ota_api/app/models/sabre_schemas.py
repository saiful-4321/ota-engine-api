from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class FlightSearchRequest(BaseModel):
    origin: str = Field(..., description="Origin airport code (IATA)")
    destination: str = Field(..., description="Destination airport code (IATA)")
    departure_date: str = Field(..., description="Departure date in YYYY-MM-DD format")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format")
    adults: int = Field(1, description="Number of adult passengers")
    children: int = Field(0, description="Number of child passengers")
    infants: int = Field(0, description="Number of infant passengers")
    cabin_class: Optional[str] = Field("Y", description="Cabin class (Y=Economy, S=Premium Economy, C=Business, J=Premium Business, F=First, P=Premium First)")
    
    # Advanced BFM Parameters
    direct_flights_only: Optional[bool] = Field(False, description="Set strictly to True to exclude connecting flights.")
    max_stops: Optional[int] = Field(None, description="Maximum number of stops allowed (e.g., 0, 1, 2).")
    included_airlines: Optional[List[str]] = Field(None, description="List of preferred airline IATA codes (e.g., ['BA', 'AA']).")
    excluded_airlines: Optional[List[str]] = Field(None, description="List of airline IATA codes to avoid.")
    flexible_dates: Optional[bool] = Field(False, description="Search +/- 1-3 days around the requested dates for cheaper fares.")
    corporate_code: Optional[str] = Field(None, description="Agency corporate ID or discount code.")
    account_code: Optional[str] = Field(None, description="Negotiated account code for private fares.")

class PricingRequestPassenger(BaseModel):
    passenger_type: str = Field(..., description="Type of passenger (ADT, CNN, INF)")
    quantity: int = Field(..., description="Number of passengers of this type")

class FlightPricingRequest(BaseModel):
    flight_segments: List[Dict[str, Any]] = Field(..., description="List of flight segments from search response")
    passengers: List[PricingRequestPassenger] = Field(..., description="List of passenger counts and types")

class BookingPassenger(BaseModel):
    first_name: str
    last_name: str
    passenger_type: str = Field(..., description="ADT, CNN, INF")
    gender: str = Field(..., description="M or F")
    date_of_birth: str = Field(..., description="YYYY-MM-DD")
    email: Optional[str] = None
    phone: Optional[str] = None
    document_number: Optional[str] = None # Passport or ID
    document_expiry: Optional[str] = None # YYYY-MM-DD
    document_issue_country: Optional[str] = None # Country code
    nationality: Optional[str] = None # Country code

class FlightBookingRequest(BaseModel):
    flight_segments: List[Dict[str, Any]] = Field(..., description="Flight segments to book")
    passengers: List[BookingPassenger] = Field(..., description="Passenger details for the booking")
    price_info: Dict[str, Any] = Field(..., description="Pricing information verified previously")
    validating_carrier: Optional[str] = Field(None, description="Optional airline code to use as validating carrier for pricing")

class TicketingRequest(BaseModel):
    pnr: str = Field(..., description="Passenger Name Record (PNR) locator to ticket")
    country_code: Optional[str] = Field("BD", description="Two-letter country code for ticketing (default is BD for Bangladesh)")
    printer_id: Optional[str] = Field(None, description="Optional specific printer LNIATA or ID")
    validating_carrier: Optional[str] = Field(None, description="Optional two-letter airline code to use as validating carrier")

class PNRDetailsRequest(BaseModel):
    pnr: str = Field(..., description="Passenger Name Record (PNR) locator to retrieve details for")

class CancelItineraryRequest(BaseModel):
    pnr: str = Field(..., description="Passenger Name Record (PNR) locator to cancel")
    cancel_segments: Optional[bool] = Field(True, description="Cancel all flight segments")
    
class VoidTicketRequest(BaseModel):
    ticket_number: str = Field(..., description="The electronic ticket number to void")
    pnr: str = Field(..., description="The associated PNR")

class ExchangeTicketRequest(BaseModel):
    pnr: str = Field(..., description="The PNR containing the ticket to be exchanged")
    original_ticket_number: str = Field(..., description="The ticket number being exchanged")
    new_flight_segments: List[Dict[str, Any]] = Field(..., description="The new flight segments")
class SeatMapRequest(BaseModel):
    pnr: Optional[str] = Field(None, description="PNR locator if a booking exists")
    flight_segment: Dict[str, Any] = Field(..., description="Flight segment to retrieve seats for")

class BaggageAllowanceRequest(BaseModel):
    pnr: str = Field(..., description="PNR locator")

class QueueRequest(BaseModel):
    pnr: str = Field(..., description="PNR locator")
    pseudo_city_code: str = Field(..., description="Agency PCC")
    queue_number: str = Field(..., description="Queue number to place the PNR on")

class FareRulesRequest(BaseModel):
    flight_segment: Dict[str, Any] = Field(..., description="Flight segment to check rules for")

