from datetime import datetime
from sqlalchemy import Column, String, BigInteger, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase


class AtAuditEvent(OtaDbBase):
    """
    General-purpose, append-only event log for a booking.

    Captures status changes, user actions, system events, supplier
    callbacks, and any domain event worth recording.  Broader than the
    old AtBookingStatusHistory — captures *what happened* with full
    structured context.

    This table is IMMUTABLE — rows are never updated or deleted.
    """
    __tablename__ = "at_audit_events"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    booking_id  = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=False, index=True)

    # What happened
    event_type  = Column(String(50), nullable=False)   # STATUS_CHANGE | PRICE_CHANGE | PAYMENT | REFUND | REISSUE
                                                        # | TICKET_ISSUED | TICKET_VOIDED | SUPPLIER_CALLBACK
                                                        # | USER_ACTION | SYSTEM
    old_value   = Column(String(255), nullable=True)
    new_value   = Column(String(255), nullable=True)
    details     = Column(JSON, nullable=True)           # structured event data (flexible)

    # Who did it
    actor_type  = Column(String(20), nullable=True)     # USER | SYSTEM | SUPPLIER | SCHEDULER
    actor_id    = Column(String(50), nullable=True)     # user UUID, system name, etc.
    ip_address  = Column(String(45), nullable=True)

    created_at  = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    booking = relationship("AtBooking", back_populates="audit_events")
