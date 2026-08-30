from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, ForeignKey, Date, CHAR
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase


class AtBookingJourney(OtaDbBase):
    """
    Represents one origin-to-destination travel unit within a booking.
    Groups segments that together form a single priced fare.

    Examples:
      One-way DAC → DXB:           1 Journey, 1+ Segments
      Round-trip DAC → DXB → DAC:  2 Journeys, each with 1+ Segments
      Multi-city DAC → DXB → LHR:  2+ Journeys
    """
    __tablename__ = "at_booking_journeys"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    booking_id       = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    journey_sequence = Column(Integer, nullable=False, default=1)
    direction        = Column(String(10), nullable=True)   # OUTBOUND | INBOUND | NULL (multi-city)
    origin           = Column(CHAR(3), nullable=False, index=True)
    destination      = Column(CHAR(3), nullable=False, index=True)
    departure_date   = Column(Date, nullable=False)
    created_at       = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    booking  = relationship("AtBooking", back_populates="journeys")
    segments = relationship("AtBookingSegment", back_populates="journey", cascade="all, delete-orphan")
