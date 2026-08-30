from pydantic import BaseModel, Field, validator, root_validator
from typing import List, Optional, Dict, Any


class MultiCitySegment(BaseModel):
    origin: str = Field(..., description="Origin airport IATA code")
    destination: str = Field(..., description="Destination airport IATA code")
    departure_date: str = Field(..., description="Departure date in YYYY-MM-DD format")


class FlightSearchRequest(BaseModel):
    # Trip type: one_way | round_trip | multi_city
    trip_type: Optional[str] = Field("one_way", description="Trip type: one_way, round_trip, or multi_city")

    # One-way / Round-trip fields (required unless trip_type is multi_city)
    origin: Optional[str] = Field(None, description="Origin airport code (IATA) — required for one_way/round_trip")
    destination: Optional[str] = Field(None, description="Destination airport code (IATA) — required for one_way/round_trip")
    departure_date: Optional[str] = Field(None, description="Departure date in YYYY-MM-DD format — required for one_way/round_trip")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format (round_trip only)")

    # Multi-city segments (required when trip_type is multi_city)
    segments: Optional[List[MultiCitySegment]] = Field(None, description="List of flight legs for multi-city searches")

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
    currency: Optional[str] = Field("BDT", description="Preferred currency code (e.g., USD, EUR, BDT)")

    @root_validator
    def validate_trip_fields(cls, values):
        trip_type = values.get("trip_type", "one_way")
        if trip_type == "multi_city":
            segments = values.get("segments")
            if not segments or len(segments) < 2:
                raise ValueError("multi_city searches require at least 2 segments")
        else:
            if not values.get("origin"):
                raise ValueError("'origin' is required for one_way/round_trip searches")
            if not values.get("destination"):
                raise ValueError("'destination' is required for one_way/round_trip searches")
            if not values.get("departure_date"):
                raise ValueError("'departure_date' is required for one_way/round_trip searches")
        return values

class PricingRequestPassenger(BaseModel):
    passenger_type: str = Field(..., description="Type of passenger (ADT, CNN, INF)")
    quantity: int = Field(..., description="Number of passengers of this type")

class FlightPricingRequest(BaseModel):
    flight_segments: List[Dict[str, Any]] = Field(..., description="List of flight segments from search response")
    passengers: List[PricingRequestPassenger] = Field(..., description="List of passenger counts and types")
    currency: Optional[str] = Field("BDT", description="Currency code for revalidation (e.g., USD, BDT)")

class AtBookingPassenger(BaseModel):
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
    passengers: List[AtBookingPassenger] = Field(..., description="Passenger details for the booking")
    price_info: Dict[str, Any] = Field(
        ...,
        description=(
            "Pricing information verified previously. "
            "Expected keys: total_fare, base_fare, tax_amount, service_fee, discount_amount, currency. "
            "Optionally include 'taxes': [{'code': 'YQ', 'amount': 1500}, ...] for detailed tax breakdown. "
            "For non-BDT currencies, also supply `conversion_rate_to_bdt` (float) — "
            "e.g. if currency='USD' and 1 USD = 110.50 BDT, set conversion_rate_to_bdt=110.50. "
            "All amounts are stored in BDT internally; the original currency and rate are preserved for audit."
        )
    )
    validating_carrier: Optional[str] = Field(None, description="Optional airline code to use as validating carrier for pricing")

class TicketingRequest(BaseModel):
    pnr: str = Field(..., description="Passenger Name Record (PNR) locator to ticket")
    country_code: Optional[str] = Field("BD", description="Two-letter country code for ticketing (default is BD for Bangladesh)")
    printer_id: Optional[str] = Field(None, description="Optional specific printer LNIATA or ID")
    validating_carrier: Optional[str] = Field(None, description="Optional two-letter airline code to use as validating carrier")
    fop_type: Optional[str] = Field("CA", description="Form of payment type (CA=Cash, CC=Credit Card, CK=Check)")
    commission_percent: Optional[float] = Field(7, description="Commission percentage to apply on ticketing")
    reissue: Optional[bool] = Field(False, description="Whether this is a reissue ticketing")
    quote_number: Optional[int] = Field(1, description="Price quote record number to use for ticketing (defaults to 1, use the number returned by reprice)")

class RepricePNRRequest(BaseModel):
    pnr: str = Field(..., description="Passenger Name Record (PNR) locator to reprice")
    passenger_types: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Passenger type counts e.g. [{\"Code\": \"ADT\", \"Quantity\": \"1\"}]. Defaults to 1 adult."
    )


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

