import sys
import os

# Add current directory to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.models.sabre_schemas import FlightSearchRequest
from app.services.sabre_service import SabreFlightService

def main():
    service = SabreFlightService()
    
    # A standard search request
    req = FlightSearchRequest(
        origin="JFK",
        destination="LHR",
        departure_date="2026-12-01",
        adults=1
    )
    
    try:
        response = service.search_flights(req)
        print("Success! Result:")
        print(response)
    except Exception as e:
        print(f"Exception caught: {e}")

if __name__ == "__main__":
    main()
