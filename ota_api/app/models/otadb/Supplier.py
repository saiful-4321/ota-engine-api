import uuid
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, Boolean
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

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid          = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    name          = Column(String(50), nullable=False, unique=True)
    code          = Column(String(20), nullable=False, unique=True)       # 'sabre', 'amadeus'
    supplier_type = Column(String(20), nullable=True, default='GDS')      # GDS|NDC|DIRECT|CONSOLIDATOR
    description   = Column(String(255), nullable=True)
    is_active     = Column(Integer, default=1)   # Using Integer for BOOLEAN compat
    created_at    = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at    = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
