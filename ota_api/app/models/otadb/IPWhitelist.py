from sqlalchemy import Column, Integer, String, TIMESTAMP, BigInteger, text, func, Boolean, DateTime, Text
from databases.database import OtaDbBase
from datetime import datetime

class IPWhitelist(OtaDbBase):
    __tablename__ = 'ip_whitelists'

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), nullable=False)
    entity_type = Column(String(50), nullable=False)  # e.g., user
    entity_id = Column(BigInteger, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(BigInteger, nullable=True)
    updated_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())