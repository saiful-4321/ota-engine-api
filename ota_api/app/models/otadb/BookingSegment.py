from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, ForeignKey, Text
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class BookingSegment(OtaDbBase):
    __tablename__ = "booking_segments"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    booking_id          = Column(String(36), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
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

    # Relationships
    booking = relationship("Booking", back_populates="segments")
