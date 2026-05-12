from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, func
from databases.database import OtaDbBase
from sqlalchemy.sql import expression

class Country(OtaDbBase):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True, nullable=False)
    iso2 = Column(String(2), unique=True, index=True, nullable=True)
    iso3 = Column(String(3), unique=True, index=True, nullable=True)
    phone_code = Column(String(20), nullable=True)
    region = Column(String(100), nullable=True)
    currency = Column(String(10), nullable=True)
    flag = Column(String(255), nullable=True)
    zone_name = Column(String(255), nullable=True)
    gmt_offset_name = Column(String(100), nullable=True)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    status = Column(String(20), default='Active')
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)
