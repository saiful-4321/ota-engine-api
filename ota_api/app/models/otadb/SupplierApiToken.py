from sqlalchemy import Column, String, BigInteger, TIMESTAMP, Text, ForeignKey
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase
from datetime import datetime

class SupplierApiToken(OtaDbBase):
    """
    Supplier API Token configuration to store authorization tokens.
    """
    __tablename__ = "supplier_api_tokens"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    supplier_id  = Column(BigInteger, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    token_key    = Column(String(255), nullable=False, index=True)
    access_token = Column(Text, nullable=False)
    expires_at   = Column(TIMESTAMP, nullable=True)
    created_at   = Column(TIMESTAMP, nullable=True, default=datetime.utcnow)
    updated_at   = Column(TIMESTAMP, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    supplier     = relationship("Supplier", back_populates="api_tokens")
