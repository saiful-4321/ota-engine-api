from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP
from databases.database import OtaDbBase
from datetime import datetime

class Supplier(OtaDbBase):
    __tablename__ = "suppliers"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    name        = Column(String(50), nullable=False, unique=True)
    code        = Column(String(20), nullable=False, unique=True) # e.g., 'sabre', 'amadeus'
    description = Column(String(255), nullable=True)
    is_active   = Column(Integer, default=1) # Using Integer for BOOLEAN compatibility if needed
    created_at  = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at  = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
