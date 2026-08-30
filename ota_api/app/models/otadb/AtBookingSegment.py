from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, ForeignKey, Text
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class AtBookingSegment(OtaDbBase):
    """
    Represents one non-stop flight leg — the atomic unit of air travel.

    Segments are grouped by Journey. A connecting itinerary (DAC → SIN → LHR)
    has 2 segments within 1 journey.

    segment_status lifecycle:
      CONFIRMED → FLOWN | CANCELLED
    """
    __tablename__ = "at_booking_segments"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    booking_id          = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    journey_id          = Column(BigInteger, ForeignKey("at_booking_journeys.id", ondelete="CASCADE"), nullable=True, index=True)

    # Ordering
    segment_number      = Column(Integer, nullable=False)       # Global order within booking (legacy)
    segment_sequence    = Column(Integer, nullable=True)        # Order within journey (new)

    # Flight identity
    carrier_code        = Column(String(3), nullable=False, index=True)   # Primary carrier (marketing)
    marketing_carrier   = Column(String(3), nullable=True)
    operating_carrier   = Column(String(3), nullable=True)
    flight_number       = Column(String(10), nullable=False)

    # Route
    origin              = Column(String(3), nullable=False, index=True)
    destination         = Column(String(3), nullable=False, index=True)

    # Times
    departure_at        = Column(TIMESTAMP, nullable=False, index=True)
    arrival_at          = Column(TIMESTAMP, nullable=False)

    # Terminal / Aircraft
    terminal_departure  = Column(String(10), nullable=True)
    terminal_arrival    = Column(String(10), nullable=True)
    aircraft_code       = Column(String(10), nullable=True)

    # Fare / Class
    cabin_class         = Column(String(20), nullable=True)     # Y|S|C|J|F|P
    booking_class       = Column(String(10), nullable=True)     # RBD e.g. "Y", "B", "M"
    fare_basis          = Column(String(50), nullable=True)

    # Status & Metadata
    segment_status      = Column(String(50), nullable=True, default='CONFIRMED')
    stop_quantity       = Column(Integer, default=0, nullable=True)
    duration_minutes    = Column(Integer, nullable=True)
    baggage_allowance   = Column(String(50), nullable=True)
    baggage_info        = Column(Text, nullable=True)           # Legacy: free-text baggage

    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Legacy fields (kept for backward compat)
    segment_order       = Column(Integer, default=1, nullable=True)
    departure_airport   = Column(String(3), nullable=True)      # Legacy alias for origin
    arrival_airport     = Column(String(3), nullable=True)      # Legacy alias for destination
    departure_time      = Column(TIMESTAMP, nullable=True)      # Legacy alias for departure_at
    arrival_time        = Column(TIMESTAMP, nullable=True)      # Legacy alias for arrival_at
    duration            = Column(String(255), nullable=True)    # Legacy: string duration
    status              = Column(String(2), nullable=True)      # Legacy: short status code

    # Detailed Location Info (per user request)
    departure_airport_name = Column(String(255), nullable=True)
    arrival_airport_name   = Column(String(255), nullable=True)
    departure_city_name    = Column(String(255), nullable=True)
    arrival_city_name      = Column(String(255), nullable=True)

    # Dynamic alias property (legacy)
    @property
    def flight_booking_id(self):
        return self.booking_id

    @flight_booking_id.setter
    def flight_booking_id(self, value):
        self.booking_id = value

    # ── Relationships ──────────────────────────────────────────────────────
    booking = relationship("AtBooking", back_populates="segments")
    journey = relationship("AtBookingJourney", back_populates="segments")
    coupons = relationship("AtTicketCoupon", back_populates="segment")
