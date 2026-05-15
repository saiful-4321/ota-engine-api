from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class SupplierLog(OtaDbBase):
    __tablename__ = "supplier_logs"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    supplier_id         = Column(BigInteger, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    
    endpoint            = Column(Text, nullable=True)
    request_payload     = Column(JSON, nullable=True)
    response_payload    = Column(JSON, nullable=True)
    response_time_ms    = Column(Integer, nullable=True)
    status_code         = Column(Integer, nullable=True)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    supplier = relationship("Supplier")
