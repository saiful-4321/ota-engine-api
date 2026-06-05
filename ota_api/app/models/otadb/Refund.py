import uuid
from datetime import datetime
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class Refund(OtaDbBase):
    __tablename__ = "refunds"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id          = Column(BigInteger, ForeignKey("bookings.id"), nullable=False, index=True)
    ticket_id           = Column(BigInteger, ForeignKey("tickets.id"), nullable=False, index=True)
    
    refund_status       = Column(String(50), nullable=True)
    refund_amount       = Column(DECIMAL(12,2), nullable=True)
    airline_penalty     = Column(DECIMAL(12,2), nullable=True)
    service_charge      = Column(DECIMAL(12,2), nullable=True)
    supplier_reference  = Column(String(100), nullable=True)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    booking = relationship("Booking")
    ticket  = relationship("Ticket")
