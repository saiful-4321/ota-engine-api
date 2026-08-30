import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, ForeignKey, DECIMAL, Boolean, CHAR, NUMERIC
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class AtPricingSnapshot(OtaDbBase):
    """
    A complete, immutable capture of all pricing at a point in time.

    Every financial event (booking, ticketing, refund, reissue) creates
    a new snapshot.  The active snapshot is the current truth.  Older
    snapshots provide audit history.

    operation values:
      SEARCH | PRICE_CONFIRMATION | REPRICE | BOOK | PAYMENT | TICKET | POST-TICKETING | CANCEL | VOID | REFUND | REISSUE | SETTLEMENT

    Immutability:  Once created, a snapshot is NEVER edited.
    It is superseded by setting is_active = False and status = 'SUPERSEDED' and creating a new version.
    """
    __tablename__ = "at_pricing_snapshots"

    id                      = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                    = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id              = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_transaction_id = Column(BigInteger, ForeignKey("supplier_transactions.id", ondelete="SET NULL"), nullable=True, index=True)
    supplier_id             = Column(BigInteger, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    
    operation               = Column(String(30), nullable=False)         
    source                  = Column(String(50), nullable=False, default='SYSTEM')
    created_by              = Column(String(100), nullable=False, default='SYSTEM')
    status                  = Column(String(20), nullable=False, default='ACTIVE')
    
    version                 = Column(Integer, nullable=False, default=1)
    is_active               = Column(Boolean, nullable=False, default=True)

    # Currency context
    base_currency           = Column(CHAR(3), nullable=False, default='BDT')
    search_currency         = Column(CHAR(3), nullable=True)             # What the user searched in
    conversion_rate         = Column(NUMERIC(18, 6), nullable=True, default=1.000000)  # search_currency → base_currency

    # Totals (in base_currency)
    supplier_total          = Column(DECIMAL(18, 4), nullable=False, default=0.0000)   # Cost to OTA
    customer_total          = Column(DECIMAL(18, 4), nullable=False, default=0.0000)   # Charged to customer
    commission_total        = Column(DECIMAL(18, 4), nullable=False, default=0.0000)   # OTA earnings
    
    created_at              = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    booking              = relationship("AtBooking", back_populates="pricing_snapshots")
    supplier_transaction = relationship("SupplierTransaction")
    components           = relationship("AtPricingComponent", back_populates="snapshot", cascade="all, delete-orphan")
