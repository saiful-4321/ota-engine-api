from sqlalchemy import Column, String, BigInteger, ForeignKey, DECIMAL, Boolean, CHAR, Integer
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class AtPricingComponent(OtaDbBase):
    """
    A single financial line item within a PricingSnapshot.

    component_type hierarchy:
      BASE_FARE         — airline base fare
      TAX               — government/airport/airline tax (subtype = tax code: YQ, BD, etc.)
      FEE               — OTA/supplier fee (subtype = ISSUANCE, SERVICE, CHANGE, etc.)
      MARKUP            — OTA commercial margin
      DISCOUNT          — price reduction (promo, loyalty, agent override)
      COMMISSION        — airline commission to OTA (internal)
      PENALTY           — cancellation/change penalty
      ANCILLARY         — ancillary service charge
      FARE_DIFFERENCE   — fare delta during reissue
      TAX_DIFFERENCE    — tax delta during reissue
      VOID_FEE          — supplier/OTA void penalty

    scope:
      SUPPLIER  — cost the OTA pays to the airline
      CUSTOMER  — amount the OTA charges the traveller
      INTERNAL  — OTA's own revenue/cost (commission, internal fees)

    direction:
      DEBIT     — charge (increases total)
      CREDIT    — reduction (decreases total)

    Scoping via nullable FKs:
      passenger_id  — scopes this component to a specific passenger
      segment_id    — scopes this component to a specific segment
      journey_id    — scopes this component to a specific journey
      All NULL      — component applies to entire booking

    Immutability:  Components are NEVER edited. They belong to an
    immutable PricingSnapshot.
    """
    __tablename__ = "at_pricing_components"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    pricing_snapshot_id = Column(BigInteger, ForeignKey("at_pricing_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # What kind of charge
    component_type      = Column(String(50), nullable=False)    # BASE_FARE|TAX|FEE|MARKUP|DISCOUNT|COMMISSION|PENALTY|ANCILLARY|FARE_DIFFERENCE|TAX_DIFFERENCE|VOID_FEE
    component_subtype   = Column(String(50), nullable=True)     # Tax code (YQ, BD), fee type (ISSUANCE), etc.
    code                = Column(String(20), nullable=True)     # Specific code for this item
    scope               = Column(String(20), nullable=False)    # SUPPLIER|CUSTOMER|INTERNAL
    direction           = Column(String(10), nullable=False)    # DEBIT|CREDIT
    source              = Column(String(50), nullable=True)     # AIRLINE|OTA|PAYMENT_GATEWAY|GOVERNMENT

    # Amounts
    amount              = Column(DECIMAL(18, 4), nullable=False)          # In base_currency (BDT)
    original_amount     = Column(DECIMAL(18, 4), nullable=True)           # Exact amount in source currency
    original_currency   = Column(CHAR(3), nullable=True)                  # e.g. USD
    exchange_rate       = Column(DECIMAL(18, 6), nullable=True, default=1.000000)
    converted_amount    = Column(DECIMAL(18, 4), nullable=True)
    converted_currency  = Column(CHAR(3), nullable=True, default='BDT')
    currency_code       = Column(CHAR(3), nullable=False, default='BDT')  # Legacy field, kept for compat

    # Derived Mathematics
    quantity            = Column(Integer, nullable=True, default=1)       # Multiplier
    percentage          = Column(DECIMAL(8, 4), nullable=True)            # If derived via %, what was it?
    calculation_basis   = Column(DECIMAL(18, 4), nullable=True)           # What the % was applied to

    # Metadata
    description         = Column(String(255), nullable=True)              # Human-readable label
    is_refundable       = Column(Boolean, nullable=True, default=True)    # Critical for refund calculations

    # Scoping FKs (all nullable — NULL means booking-level)
    passenger_id        = Column(BigInteger, ForeignKey("at_booking_passengers.id", ondelete="SET NULL"), nullable=True, index=True)
    segment_id          = Column(BigInteger, ForeignKey("at_booking_segments.id", ondelete="SET NULL"), nullable=True, index=True)
    journey_id          = Column(BigInteger, ForeignKey("at_booking_journeys.id", ondelete="SET NULL"), nullable=True, index=True)
    supplier_id         = Column(BigInteger, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    ticket_id           = Column(BigInteger, ForeignKey("at_flight_tickets.id", ondelete="SET NULL"), nullable=True, index=True)

    # Generic polymorphic reference (for linking to ancillary, penalty source, etc.)
    reference_type      = Column(String(100), nullable=True)
    reference_id        = Column(BigInteger, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    snapshot  = relationship("AtPricingSnapshot", back_populates="components")
    passenger = relationship("AtBookingPassenger")
    segment   = relationship("AtBookingSegment")
    journey   = relationship("AtBookingJourney")
    supplier  = relationship("Supplier")
    ticket    = relationship("AtFlightTicket")
