from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Boolean, func
from databases.database import OtaDbBase
from sqlalchemy.orm import relationship

class Airport(OtaDbBase):
    __tablename__ = "airports"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), index=True, nullable=False)
    iata_code = Column(String(3), unique=True, index=True, nullable=False)
    icao_code = Column(String(10), index=True, nullable=True)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    timezone = Column(String(100), nullable=True)
    is_international = Column(Boolean, default=False, index=True)
    status = Column(String(20), default='Active')
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    city = relationship("City", backref="airports")
    country = relationship("Country", backref="airports")
