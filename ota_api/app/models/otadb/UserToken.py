# models.UserToken.py
from sqlalchemy import Column, Integer, String, BigInteger, Enum, DateTime, Boolean
from databases.database import OtaDbBase
from datetime import datetime
from enum import Enum as PyEnum
from app.models.enums import UserDevices

class UserTokenStatus(str, PyEnum):
    VALID = "Valid"
    EXPIRED = "Expired"

class UserTokenType(str, PyEnum):
    JWT = "jwt"
    SESSION = "session"

class UserToken(OtaDbBase):
    __tablename__ = "user_tokens"

    id = Column(Integer, primary_key=True)
    username = Column(String, index=True)
    user_id = Column(BigInteger, index=True)
    token = Column(String, index=True)
    refresh_token = Column(String, index=True)
    token_type = Column(Enum(UserTokenType, values_callable=lambda enum: [e.value for e in enum], native_enum=False), nullable=True)
    device = Column(Enum(UserDevices, values_callable=lambda enum: [e.value for e in enum], native_enum=False), nullable=True)
    agents = Column(String(255), nullable=True)
    is_sync_token = Column(Boolean, nullable=False, default=False)
    status = Column(Enum(UserTokenStatus, values_callable=lambda enum: [e.value for e in enum], native_enum=False), default=UserTokenStatus.VALID, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
