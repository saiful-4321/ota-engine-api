from datetime import datetime
from sqlalchemy import Column, String, BigInteger, ForeignKey, DECIMAL, TIMESTAMP
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class AtFlightReissue(OtaDbBase):
    """
    Records an exchange/reissue event. Links the original ticket to the
    new ticket, captures the fare difference, change penalty, and tax
    difference.  Creates a new PricingSnapshot.

    Status lifecycle:
      QUOTED → CONFIRMED → TICKETED
      QUOTED → CANCELLED
    """
    __tablename__ = "at_flight_reissues"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    booking_id          = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    original_ticket_id  = Column(BigInteger, ForeignKey("at_flight_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    new_ticket_id       = Column(BigInteger, ForeignKey("at_flight_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    pricing_snapshot_id = Column(BigInteger, ForeignKey("at_pricing_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    
    status              = Column(String(20), nullable=False, default='QUOTED')

    # Financial details are strictly stored in the PricingSnapshot components.
    
    supplier_reference  = Column(String(100), nullable=True)
    actioned_by         = Column(BigInteger, nullable=True)

    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Relationships ──────────────────────────────────────────────────────
    booking          = relationship("AtBooking", back_populates="flight_reissues")
    original_ticket  = relationship("AtFlightTicket", foreign_keys=[original_ticket_id])
    new_ticket       = relationship("AtFlightTicket", foreign_keys=[new_ticket_id])
    pricing_snapshot = relationship("AtPricingSnapshot")
