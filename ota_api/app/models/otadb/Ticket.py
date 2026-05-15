import uuid
from datetime import datetime
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, Enum
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class Ticket(OtaDbBase):
    __tablename__ = "tickets"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_id          = Column(String(36), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    passenger_id        = Column(String(36), ForeignKey("booking_passengers.id"), nullable=False, index=True)
    
    ticket_number       = Column(String(20), nullable=False, unique=True, index=True)
    ticket_status       = Column(Enum(
                            'ISSUED',
                            'VOID',
                            'REFUNDED',
                            'EXCHANGED',
                            name='ticket_status_enum'
                        ), nullable=False, default='ISSUED')
    
    validating_carrier  = Column(String(2), nullable=True)
    supplier_ticket_id  = Column(String(100), nullable=True)
    issue_date          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    booking   = relationship("Booking", back_populates="tickets")
    passenger = relationship("BookingPassenger", back_populates="tickets")
