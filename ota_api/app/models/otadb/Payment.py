import uuid
from datetime import datetime
from sqlalchemy import Column, String, DECIMAL, NUMERIC, TIMESTAMP, ForeignKey, Enum, JSON, BigInteger, CHAR
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class Payment(OtaDbBase):
    """
    Records a financial settlement: money collected from the customer
    or money returned to the customer.

    payment_type:
      COLLECTION            — initial booking payment
      ADDITIONAL_COLLECTION — top-up for reissue fare difference
      REFUND_RETURN         — money returned for refund

    payment_status lifecycle:
      PENDING → CAPTURED → SETTLED
      PENDING → FAILED
    """
    __tablename__ = "payments"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid             = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id       = Column(BigInteger, ForeignKey("at_bookings.id"), nullable=False, index=True)
    refund_id        = Column(BigInteger, ForeignKey("at_refunds.id", ondelete="SET NULL"), nullable=True, index=True)

    # Classification
    payment_type     = Column(String(20), nullable=True, default='COLLECTION')  # COLLECTION|ADDITIONAL_COLLECTION|REFUND_RETURN
    payment_method   = Column(String(50), nullable=True)      # CASH|BKASH|CARD|BANK_TRANSFER|...
    payment_gateway  = Column(String(50), nullable=True)
    gateway_transaction_id = Column(String(255), nullable=True, unique=True)
    
    payment_status   = Column(Enum(
                         'PENDING',
                         'PAID',
                         'CAPTURED',
                         'SETTLED',
                         'FAILED',
                         'REFUNDED',
                         'PARTIAL_REFUND',
                         name='payment_status_enum'
                     ), nullable=False, default='PENDING', index=True)

    # Amounts
    paid_amount      = Column(DECIMAL(18, 4), nullable=False)
    currency         = Column(CHAR(3), nullable=False, default='BDT', server_default='BDT')
    original_currency = Column(CHAR(3), nullable=True, default='BDT', server_default='BDT')
    original_amount   = Column(DECIMAL(18, 4), nullable=True, default=0.00, server_default='0.00')
    conversion_rate   = Column(NUMERIC(18, 6), nullable=True, default=1.0, server_default='1.000000')

    gateway_response = Column(JSON, nullable=True)
    settled_at       = Column(TIMESTAMP, nullable=True)
    created_at       = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at       = Column(TIMESTAMP, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Legacy alias — the old FK column name was `transaction_id`
    @property
    def transaction_id(self):
        return self.gateway_transaction_id

    @transaction_id.setter
    def transaction_id(self, value):
        self.gateway_transaction_id = value

    # ── Relationships ──────────────────────────────────────────────────────
    booking = relationship("AtBooking", back_populates="payments")
    refund  = relationship("AtRefund", back_populates="payments")
