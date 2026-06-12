from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, ForeignKey, Text
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class BookingSegment(OtaDbBase):
    __tablename__ = "booking_segments"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    booking_id          = Column(BigInteger, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_number      = Column(Integer, nullable=False)
    airline_code        = Column(String(2), nullable=False, index=True)
    flight_number       = Column(String(10), nullable=False)
    origin              = Column(String(3), nullable=False, index=True)
    destination         = Column(String(3), nullable=False, index=True)
    departure_datetime  = Column(TIMESTAMP, nullable=False, index=True)
    arrival_datetime    = Column(TIMESTAMP, nullable=False)
    booking_class       = Column(String(10), nullable=True)
    cabin_class         = Column(String(20), nullable=True)
    baggage_info        = Column(Text, nullable=True)
    fare_basis          = Column(String(50), nullable=True)
    segment_status      = Column(String(50), nullable=True)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Laravel-specific fields
    segment_order       = Column(Integer, default=1, nullable=True)
    marketing_carrier   = Column(String(3), nullable=True)
    operating_carrier   = Column(String(3), nullable=True)
    departure_airport   = Column(String(3), nullable=True)
    arrival_airport     = Column(String(3), nullable=True)
    terminal_departure  = Column(String(255), nullable=True)
    terminal_arrival    = Column(String(255), nullable=True)
    departure_time      = Column(TIMESTAMP, nullable=True)
    arrival_time        = Column(TIMESTAMP, nullable=True)
    duration            = Column(String(255), nullable=True)
    status              = Column(String(2), nullable=True)
    stop_quantity       = Column(Integer, default=0, nullable=True)
    baggage_allowance   = Column(String(255), nullable=True)
    aircraft_code       = Column(String(255), nullable=True)

    # Dynamic alias property
    @property
    def flight_booking_id(self):
        return self.booking_id

    @flight_booking_id.setter
    def flight_booking_id(self, value):
        self.booking_id = value

    # Relationships
    booking = relationship("Booking", back_populates="segments")
