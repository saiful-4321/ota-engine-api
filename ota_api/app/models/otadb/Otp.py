# models.Otp.py
from sqlalchemy import Column, Integer, String, BigInteger, Enum, DateTime
from databases.database import OtaDbBase
from datetime import datetime, timedelta
from enum import Enum as PyEnum
from config import OTP_EXPIRES_TIME

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
    expired_time = Column(DateTime, default=datetime.utcnow() + timedelta(minutes=OTP_EXPIRES_TIME))
    expires_at = Column(DateTime, default=datetime.utcnow() + timedelta(minutes=OTP_EXPIRES_TIME))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
