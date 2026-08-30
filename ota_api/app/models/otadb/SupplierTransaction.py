from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class SupplierTransaction(OtaDbBase):
    """
    An immutable audit record of every API call made to an external supplier.

    This is the ISOLATION BOUNDARY for supplier-specific data. All GDS/NDC
    specific references (PNR, PCC, office_id, gds_source) live here, NOT
    on the Booking entity.

    operation values:
      SEARCH | PRICE | BOOK | TICKET | VOID | CANCEL | EXCHANGE |
      REPRICE | SEAT_MAP | BAGGAGE | FARE_RULES | QUEUE

    Immutability:  Rows are NEVER updated. Append-only log.
    """
    __tablename__ = "supplier_transactions"

    id                   = Column(BigInteger, primary_key=True, autoincrement=True)
    supplier_id          = Column(BigInteger, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    booking_id           = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=True, index=True)
    
    operation            = Column(String(50), nullable=False)           # SEARCH|PRICE|BOOK|TICKET|VOID|CANCEL|...

    # Supplier-specific references (the isolation boundary)
    supplier_booking_ref = Column(String(100), nullable=True, index=True)   # PNR (GDS) or Order ID (NDC)
    supplier_order_id    = Column(String(100), nullable=True)               # NDC order reference
    pcc                  = Column(String(20), nullable=True)                # Pseudo City Code (GDS)
    office_id            = Column(String(50), nullable=True)                # Office ID (Amadeus/NDC)
    gds_source           = Column(String(10), nullable=True)                # 1S (Sabre), 1A (Amadeus), etc.

    # Request/Response capture
    req_payload_uri      = Column(String(512), nullable=True)               # S3/disk path to full request
    res_payload_uri      = Column(String(512), nullable=True)               # S3/disk path to full response
    supplier_metadata    = Column(JSON, nullable=True)                      # Catch-all for supplier-specific data

    # Performance & status
    http_status_code     = Column(Integer, nullable=True)
    response_time_ms     = Column(Integer, nullable=True)
    error_message        = Column(Text, nullable=True)
    
    created_at           = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # ── Relationships ──────────────────────────────────────────────────────
    supplier = relationship("Supplier")
    booking  = relationship("AtBooking", back_populates="supplier_transactions")
