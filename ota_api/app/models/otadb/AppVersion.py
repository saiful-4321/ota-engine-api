import uuid
from sqlalchemy import Column, Integer, String, BigInteger, Enum, DateTime
from databases.database import OtaDbBase

class AppVersion(OtaDbBase):
    __tablename__ = "app_versions"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    version = Column(String, index=True)
    created_at = Column(DateTime)
