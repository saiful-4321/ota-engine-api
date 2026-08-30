from datetime import datetime
from sqlalchemy import Column, BigInteger, DECIMAL, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase


class AtRefundItem(OtaDbBase):
    """
    Line-item detail for a refund — tracks which ticket (and optionally
    which coupon) is being refunded, along with the refund amount and
    penalty applied to that specific item.

    One AtRefund can have multiple AtRefundItems (e.g. refunding 3
    passengers means 3 items, each with their own penalty calculation).
    """
    __tablename__ = "at_refund_items"

    id                = Column(BigInteger, primary_key=True, autoincrement=True)
    refund_id         = Column(BigInteger, ForeignKey("at_refunds.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id         = Column(BigInteger, ForeignKey("at_flight_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    coupon_id         = Column(BigInteger, ForeignKey("at_ticket_coupons.id", ondelete="SET NULL"), nullable=True, index=True)
    refund_amount     = Column(DECIMAL(18, 4), nullable=False, default=0.0000)
    penalty_amount    = Column(DECIMAL(18, 4), nullable=False, default=0.0000)
    tax_refund_amount = Column(DECIMAL(18, 4), nullable=False, default=0.0000)
    created_at        = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    refund = relationship("AtRefund", back_populates="items")
    ticket = relationship("AtFlightTicket")
    coupon = relationship("AtTicketCoupon")
