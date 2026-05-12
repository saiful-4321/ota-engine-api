from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, func
from databases.database import OtaDbBase
from sqlalchemy.orm import relationship

class City(OtaDbBase):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), index=True, nullable=False)
    iata_code = Column(String(3), index=True, nullable=True) # e.g., LON for London
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    status = Column(String(20), default='Active')
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    country = relationship("Country", backref="cities")
