from sqlalchemy import Column, String, BigInteger, Integer, TIMESTAMP, Text, DECIMAL, ForeignKey
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase
from datetime import datetime

class SupplierServiceLink(OtaDbBase):
    """
    Links a supplier to specific services (flight, hotel, transfer, visa)
    along with service-specific status, credential overrides, and commission overrides.
    """
    __tablename__ = "supplier_service_links"

    id                   = Column(BigInteger, primary_key=True, autoincrement=True)
    supplier_id          = Column(BigInteger, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    service              = Column(String(255), nullable=False)   # flight, hotel, transfer, visa
    status               = Column(Integer, nullable=False, default=1)   # 1=active, 0=inactive
    credentials_override = Column(Text, nullable=True)                  # Encrypted/JSON credentials override
    commission_override  = Column(DECIMAL(10, 2), nullable=True)
    created_at           = Column(TIMESTAMP, nullable=True, default=datetime.utcnow)
    updated_at           = Column(TIMESTAMP, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    supplier             = relationship("Supplier", back_populates="service_links")
