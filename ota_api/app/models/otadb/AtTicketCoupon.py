from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, ForeignKey, Date
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase


class AtTicketCoupon(OtaDbBase):
    """
    Represents one coupon within an e-ticket, corresponding to exactly one
    flight segment.  An e-ticket has 1-4 coupons (IATA limit).

    Coupon-level tracking enables:
      - Partial usage (fly outbound, cancel return)
      - Partial refunds (refund unused coupons only)
      - Exchange tracking (which coupons were exchanged)
      - Airport control status

    Status lifecycle:
      OPEN → USED | VOID | REFUNDED | EXCHANGED | AIRPORT_CONTROL | SUSPENDED
    """
    __tablename__ = "at_ticket_coupons"

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id      = Column(BigInteger, ForeignKey("at_flight_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_id     = Column(BigInteger, ForeignKey("at_booking_segments.id", ondelete="SET NULL"), nullable=True, index=True)
    coupon_number  = Column(Integer, nullable=False)          # 1–4
    coupon_status  = Column(String(20), nullable=False, default='OPEN')
    not_valid_before = Column(Date, nullable=True)
    not_valid_after  = Column(Date, nullable=True)
    
    # Legacy fields required by Laravel database
    departure_airport = Column(String(3), nullable=False)
    arrival_airport   = Column(String(3), nullable=False)
    departure_time    = Column(TIMESTAMP, nullable=False)
    carrier           = Column(String(2), nullable=False)
    flight_number     = Column(String(10), nullable=False)
    fare_basis        = Column(String(50), nullable=True)
    booking_class     = Column(String(10), nullable=True)

    created_at     = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at     = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ticket  = relationship("AtFlightTicket", back_populates="coupons")
    segment = relationship("AtBookingSegment", back_populates="coupons")
