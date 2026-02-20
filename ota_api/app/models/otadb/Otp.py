# models.Otp.py
from sqlalchemy import Column, Integer, String, BigInteger, Enum, DateTime
from databases.database import OtaDbBase
from datetime import datetime
from enum import Enum as PyEnum

class OtpStatus(str, PyEnum):
    Pending = "Pending"
    Verified = "Verified"

class Otp(OtaDbBase):
    __tablename__ = "otps"

    id = Column(Integer, primary_key=True)
    username = Column(String, index=True)
    user_id = Column(BigInteger, index=True)
    email = Column(String, index=True)
    phone = Column(String)
    otp = Column(String)
    status = Column(Enum(OtpStatus), default=OtpStatus.Pending, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
