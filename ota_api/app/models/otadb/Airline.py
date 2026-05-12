from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from databases.database import OtaDbBase
from sqlalchemy.orm import relationship

class Airline(OtaDbBase):
    __tablename__ = "airlines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True, nullable=False)
    iata_code = Column(String(2), unique=True, index=True, nullable=False)
    icao_code = Column(String(3), index=True, nullable=True)
    logo = Column(String(255), nullable=True)
    country_id = Column(Integer, ForeignKey("countries.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), default='Active')
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    country = relationship("Country", backref="airlines")
