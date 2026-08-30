import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DECIMAL, NUMERIC, TIMESTAMP, ForeignKey, Enum, BigInteger, text
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class AtBooking(OtaDbBase):
    """
    The root aggregate. Represents a single commercial transaction between
    a customer and the OTA. Groups all passengers, journeys, tickets,
    pricing, and financial events.

    Lifecycle:
      QUOTED → PENDING → CONFIRMED → TICKETED → COMPLETED → CANCELLED
    """
    __tablename__ = "at_bookings"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_reference   = Column(String(20), nullable=False, unique=True, index=True)
    user_id             = Column(BigInteger, nullable=True, index=True)
    supplier_id         = Column(BigInteger, ForeignKey("suppliers.id"), nullable=True, index=True)

    status              = Column(String(30), nullable=False, default='PENDING', index=True)
    journey_type        = Column(String(20), nullable=True)   # ONE_WAY | ROUND_TRIP | MULTI_CITY
    is_domestic         = Column(Integer, default=0, nullable=True)
    contact_email       = Column(String(255), nullable=False)
    contact_phone       = Column(String(50), nullable=False)

    # Supplier-sourced PNR (denormalized from SupplierTransaction for quick lookups)
    primary_pnr         = Column(String(10), nullable=True, index=True)
    pnr                 = Column(String(10), nullable=True, unique=True, index=True)  # Legacy: kept for backward compat
    supplier_booking_id = Column(String(100), nullable=True)

    booking_expiry      = Column(TIMESTAMP, nullable=True, server_default=text("'1970-01-01 00:00:00'"))
    issued_at           = Column(TIMESTAMP, nullable=True)
    created_by          = Column(BigInteger, nullable=True)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at          = Column(TIMESTAMP, nullable=True)

    # Legacy fields (kept for Laravel backoffice compatibility — Phase 4 cleanup)
    code                = Column(String(255), nullable=True, unique=True)
    pnr_code            = Column(String(255), nullable=True, index=True)
    airline_pnr         = Column(String(10), nullable=True)
    gds_source          = Column(String(255), nullable=True)
    airline_code        = Column(String(3), nullable=True)
    access_type         = Column(String(255), default='public', nullable=True)
    pcc                 = Column(String(20), nullable=True)
    office_id           = Column(String(50), nullable=True)
    booking_date        = Column(TIMESTAMP, nullable=True)
    ticketing_time_limit = Column(TIMESTAMP, nullable=True)
    currency_id         = Column(BigInteger, nullable=True)
    updated_by          = Column(BigInteger, nullable=True)

    # Re-added Legacy Pricing & Status fields for backward compatibility
    booking_status      = Column(String(50), nullable=True)
    payment_status      = Column(String(50), nullable=True)
    currency            = Column(String(3), nullable=True, default='BDT')
    search_currency     = Column(String(3), nullable=False, default='BDT')
    conversion_rate     = Column(DECIMAL(18, 6), nullable=False, default=1.000000)
    base_fare           = Column(DECIMAL(12, 2), nullable=False, default=0.00)
    tax_amount          = Column(DECIMAL(12, 2), nullable=False, default=0.00)
    service_fee         = Column(DECIMAL(12, 2), nullable=False, default=0.00)
    discount_amount     = Column(DECIMAL(12, 2), nullable=False, default=0.00)
    total_amount        = Column(DECIMAL(12, 2), nullable=False, default=0.00)
    other_charges       = Column(DECIMAL(12, 2), nullable=True, default=0.00)
    commission_amount   = Column(DECIMAL(12, 2), nullable=True, default=0.00)
    agency_id           = Column(BigInteger, nullable=True)
    internal_notes      = Column(String, nullable=True)
    priority            = Column(String(20), nullable=True)
    assigned_agent_id   = Column(BigInteger, nullable=True)
    tags                = Column(String, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    supplier              = relationship("Supplier")
    passengers            = relationship("AtBookingPassenger", back_populates="booking", cascade="all, delete-orphan")
    journeys              = relationship("AtBookingJourney", back_populates="booking", cascade="all, delete-orphan")
    segments              = relationship("AtBookingSegment", back_populates="booking", cascade="all, delete-orphan")
    tickets               = relationship("AtFlightTicket", back_populates="booking")
    pricing_snapshots     = relationship("AtPricingSnapshot", back_populates="booking")
    payments              = relationship("Payment", back_populates="booking")
    refunds               = relationship("AtRefund", back_populates="booking")
    flight_reissues       = relationship("AtFlightReissue", back_populates="booking")
    ancillaries           = relationship("AtAncillary", back_populates="booking")
    supplier_transactions = relationship("SupplierTransaction", back_populates="booking")
    history               = relationship("AtBookingStatusHistory", back_populates="booking")
    audit_events          = relationship("AtAuditEvent", back_populates="booking")
