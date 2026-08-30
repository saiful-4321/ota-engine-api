import uuid
from datetime import datetime
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class AtFlightTicket(OtaDbBase):
    """
    Represents an e-ticket document (13-digit number) issued to a single
    passenger.  An e-ticket is the legal contract of carriage.

    One ticket per passenger, but a passenger may have multiple tickets
    over the booking's life (original + reissued).

    The original_ticket_id self-reference links reissued tickets back
    to the ticket they replaced.

    Status lifecycle:
      ISSUED → USED | VOID | REFUNDED | EXCHANGED
    """
    __tablename__ = "at_flight_tickets"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id          = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    passenger_id        = Column(BigInteger, ForeignKey("at_booking_passengers.id"), nullable=True, index=True)
    
    ticket_number       = Column(String(20), nullable=True, unique=True, index=True)  # 13-digit e-ticket
    pnr                 = Column(String(20), nullable=True, index=True)
    fare_basis          = Column(String(50), nullable=True)
    validating_carrier  = Column(String(3), nullable=True)
    tour_code           = Column(String(20), nullable=True)
    supplier_ticket_id  = Column(String(100), nullable=True)

    status              = Column(String(20), nullable=False, default='ISSUED', index=True)

    # Self-referencing FK: links reissued ticket back to original
    original_ticket_id  = Column(BigInteger, ForeignKey("at_flight_tickets.id", ondelete="SET NULL"), nullable=True, index=True)

    # Timestamps
    issued_at           = Column(TIMESTAMP, nullable=True, default=datetime.utcnow)
    voided_at           = Column(TIMESTAMP, nullable=True)
    exchanged_at        = Column(TIMESTAMP, nullable=True)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at          = Column(TIMESTAMP, nullable=True)

    # Legacy fields (kept for Laravel backoffice compatibility)
    ticket_no           = Column(String(255), nullable=True, unique=True)
    ticket_status       = Column(String(20), nullable=True)     # Legacy alias for status
    user_id             = Column(BigInteger, nullable=True)
    assigned_to         = Column(BigInteger, nullable=True)
    category_id         = Column(BigInteger, nullable=True)
    subject             = Column(String(255), nullable=True)
    priority            = Column(String(255), default='medium', nullable=True)
    currency_id         = Column(BigInteger, nullable=True)
    created_by          = Column(BigInteger, nullable=True)     # Missing but needed for legacy insertion

    # Dynamic alias properties (legacy)
    @property
    def flight_booking_id(self):
        return self.booking_id

    @flight_booking_id.setter
    def flight_booking_id(self, value):
        self.booking_id = value

    @property
    def flight_passenger_id(self):
        return self.passenger_id

    @flight_passenger_id.setter
    def flight_passenger_id(self, value):
        self.passenger_id = value

    # ── Relationships ──────────────────────────────────────────────────────
    booking        = relationship("AtBooking", back_populates="tickets")
    passenger      = relationship("AtBookingPassenger", back_populates="tickets")
    coupons        = relationship("AtTicketCoupon", back_populates="ticket", cascade="all, delete-orphan")
    original_ticket = relationship("AtFlightTicket", remote_side=[id], foreign_keys=[original_ticket_id])
