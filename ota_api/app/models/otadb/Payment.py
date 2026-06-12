import uuid
from datetime import datetime
from sqlalchemy import Column, String, DECIMAL, NUMERIC, TIMESTAMP, ForeignKey, Enum, JSON, BigInteger
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
    
    # paid_amount  : the final settled amount converted to BDT (stored currency)
    # currency     : always 'BDT'
    # original_currency : ISO-4217 code the customer paid in (e.g. 'USD', 'SGD')
    # original_amount   : face-value amount in original_currency before conversion
    # conversion_rate   : 1 <original_currency> = <conversion_rate> BDT at payment time
    paid_amount      = Column(DECIMAL(12,2), nullable=False)
    currency         = Column(String(3), nullable=False, default='BDT', server_default='BDT')
    original_currency = Column(String(3), nullable=True,  default='BDT', server_default='BDT')
    original_amount   = Column(DECIMAL(12,2), nullable=True, default=0.00, server_default='0.00')
    conversion_rate   = Column(NUMERIC(18, 6), nullable=True, default=1.0, server_default='1.000000')
    gateway_response = Column(JSON, nullable=True)
    created_at       = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    booking = relationship("Booking", back_populates="payments")
