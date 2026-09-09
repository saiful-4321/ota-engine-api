import uuid
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, Text, DECIMAL
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase
from datetime import datetime

class Supplier(OtaDbBase):
    """
    Master data for external suppliers.

    supplier_type values:
      GDS          — Global Distribution System (Sabre, Amadeus, Travelport)
      NDC          — New Distribution Capability (airline direct)
      DIRECT       — Direct airline API (non-NDC)
      CONSOLIDATOR — Ticket consolidator
    """
    __tablename__ = "suppliers"

    id                   = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                 = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    name                 = Column(String(255), nullable=False, unique=True)
    code                 = Column(String(255), nullable=False, unique=True)       # 'sabre', 'amadeus', etc.
    supplier_type        = Column(String(20), nullable=True, default='GDS')      # GDS|NDC|DIRECT|CONSOLIDATOR
    type                 = Column(String(255), nullable=True)
    integration_provider = Column(String(50), nullable=True)
    logo                 = Column(String(255), nullable=True)
    environment          = Column(String(255), nullable=True)
    configuration        = Column(Text, nullable=True)
    is_healthy           = Column(Integer, default=1)
    circuit_status       = Column(String(255), nullable=True)
    failure_count        = Column(Integer, default=0)
    last_failure_at      = Column(TIMESTAMP, nullable=True)
    avg_response_time    = Column(DECIMAL(10, 3), nullable=True)
    last_health_check_at = Column(TIMESTAMP, nullable=True)
    currency_id          = Column(BigInteger, nullable=True)
    flight_policy_id     = Column(BigInteger, nullable=True)
    balance              = Column(DECIMAL(15, 2), default=0.00)
    credit_limit         = Column(DECIMAL(15, 2), default=0.00)
    commission_type      = Column(String(255), default='flat')
    commission_value     = Column(DECIMAL(10, 2), default=0.00)
    contact_email        = Column(String(255), nullable=True)
    contact_phone        = Column(String(255), nullable=True)
    website              = Column(String(255), nullable=True)
    status               = Column(String(20), default='Active')
    description          = Column(String(255), nullable=True)
    is_active            = Column(Integer, default=1)
    created_by           = Column(BigInteger, nullable=True)
    updated_by           = Column(BigInteger, nullable=True)
    created_at           = Column(TIMESTAMP, nullable=True, default=datetime.utcnow)
    updated_at           = Column(TIMESTAMP, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at           = Column(TIMESTAMP, nullable=True)

    # Relationships
    configuration        = relationship("SupplierConfiguration", back_populates="supplier", uselist=False, cascade="all, delete-orphan")
    service_links        = relationship("SupplierServiceLink", back_populates="supplier", cascade="all, delete-orphan")
