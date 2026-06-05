import uuid
from datetime import datetime
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey, Enum, JSON, BigInteger
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class Payment(OtaDbBase):
    __tablename__ = "payments"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid             = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id       = Column(BigInteger, ForeignKey("bookings.id"), nullable=False, index=True)
    
    payment_gateway  = Column(String(50), nullable=True)
    transaction_id   = Column(String(255), nullable=True, unique=True)
    
    payment_status   = Column(Enum(
                         'PENDING',
                         'PAID',
                         'FAILED',
                         'REFUNDED',
                         'PARTIAL_REFUND',
                         name='payment_status_enum'
                     ), nullable=False, default='PENDING', index=True)
    
    paid_amount      = Column(DECIMAL(12,2), nullable=False)
    currency         = Column(String(3), nullable=False)
    gateway_response = Column(JSON, nullable=True)
    created_at       = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    booking = relationship("Booking", back_populates="payments")
