import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, DECIMAL, TIMESTAMP, ForeignKey, CHAR
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase


class AtAncillary(OtaDbBase):
    """
    Represents a purchased add-on service: seat selection, extra baggage,
    lounge access, meal, insurance, etc.

    Each ancillary has its own pricing and may be scoped to a specific
    passenger and/or segment.

    Status lifecycle:
      REQUESTED → CONFIRMED → USED | CANCELLED | REFUNDED
    """
    __tablename__ = "at_ancillaries"

    id                 = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid               = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id         = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    passenger_id       = Column(BigInteger, ForeignKey("at_booking_passengers.id", ondelete="SET NULL"), nullable=True, index=True)
    segment_id         = Column(BigInteger, ForeignKey("at_booking_segments.id", ondelete="SET NULL"), nullable=True, index=True)
    ancillary_type     = Column(String(30), nullable=False)       # SEAT | BAGGAGE | MEAL | LOUNGE | INSURANCE | OTHER
    description        = Column(String(255), nullable=True)
    quantity           = Column(Integer, nullable=False, default=1)
    status             = Column(String(20), nullable=False, default='CONFIRMED')
    supplier_reference = Column(String(100), nullable=True)
    amount             = Column(DECIMAL(18, 4), nullable=False, default=0.0000)
    currency_code      = Column(CHAR(3), nullable=False, default='BDT')
    created_at         = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at         = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    booking   = relationship("AtBooking", back_populates="ancillaries")
    passenger = relationship("AtBookingPassenger")
    segment   = relationship("AtBookingSegment")
