from sqlalchemy import Column, Integer, String, BigInteger, Enum, DateTime
from databases.database import OtaDbBase

class AppVersion(OtaDbBase):
    __tablename__ = "app_versions"

    id = Column(Integer, primary_key=True)
    version = Column(String, index=True)
    created_at = Column(DateTime)
