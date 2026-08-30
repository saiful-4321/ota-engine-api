import uuid
from datetime import datetime
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey, BigInteger, Text
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class AtRefund(OtaDbBase):
    """
    Records a refund event against a booking.

    Links to the tickets being refunded (via AtRefundItem), the penalty
    applied, the refundable taxes, and the resulting payment.
    A refund always creates a new PricingSnapshot showing the financial impact.

    refund_type: VOLUNTARY | INVOLUNTARY | VOID | CANCELLATION

    Status lifecycle:
      INITIATED → SUPPLIER_CONFIRMED → PAYMENT_PROCESSED → COMPLETED
      INITIATED → REJECTED
    """
    __tablename__ = "at_refunds"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id          = Column(BigInteger, ForeignKey("at_bookings.id"), nullable=False, index=True)
    pricing_snapshot_id = Column(BigInteger, ForeignKey("at_pricing_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Classification
    type                = Column(String(20), nullable=False, default='cancellation')   # Legacy field
    refund_type         = Column(String(20), nullable=True, default='VOLUNTARY')       # VOLUNTARY|INVOLUNTARY|VOID
    status              = Column(String(20), nullable=False, default='INITIATED', index=True)

    # Financial summary is strictly stored in the PricingSnapshot components.
    
    supplier_reference  = Column(String(100), nullable=True)
    reason              = Column(String(255), nullable=True)
    remarks             = Column(Text, nullable=True)
    actioned_by         = Column(BigInteger, nullable=True)

    completed_at        = Column(TIMESTAMP, nullable=True)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at          = Column(TIMESTAMP, nullable=True)

    # Legacy fields
    pcc                 = Column(String(20), nullable=True)

    # Dynamic alias properties (legacy)
    @property
    def flight_booking_id(self):
        return self.booking_id

    @flight_booking_id.setter
    def flight_booking_id(self, value):
        self.booking_id = value

    @property
    def snapshot_id(self):
        return self.pricing_snapshot_id

    @snapshot_id.setter
    def snapshot_id(self, value):
        self.pricing_snapshot_id = value

    # ── Relationships ──────────────────────────────────────────────────────
    booking  = relationship("AtBooking", back_populates="refunds")
    snapshot = relationship("AtPricingSnapshot")
    items    = relationship("AtRefundItem", back_populates="refund", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="refund")
