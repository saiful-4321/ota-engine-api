# models.User.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, BigInteger, func
from sqlalchemy.sql import expression
from databases.database import OtaDbBase
from enum import Enum

class User(OtaDbBase):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True)
    
    name = Column(String(128), index=True)
    email = Column(String(128), unique=True, index=True)
    username = Column(String, unique=True, index=True, nullable=True)
    password = Column(String, nullable=True)
    phone = Column(String(20), unique=True, index=True)
    photo = Column(String, nullable=True)
    nid = Column(String(20), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
    api_token = Column(String(100), nullable=True)
    status = Column(String, default='Active')  # Active / Inactive
    user_type = Column(String, nullable=True, index=True)

    language = Column(String(5), default='en', nullable=True)
    timezone = Column(String(50), default='UTC', nullable=True)
    currency_id = Column(BigInteger, nullable=True)

    # Login & Activity Tracking
    max_login = Column(Integer, default=0)
    logged_in = Column(Integer, default=0)
    last_login = Column(String, nullable=True)
    login_ip = Column(String(45), nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)

    # Mobile Specific
    max_login_mobile = Column(Integer, default=0)
    logged_in_mobile = Column(Integer, default=0)
    total_max_login = Column(Integer, default=0)
    total_logged_in = Column(Integer, default=0)
    fcm_token = Column(String, nullable=True)

    # Flags
    first_login = Column(Boolean, default=True)
    is_tc_accepted = Column(Boolean, default=False)
    is_2fa_enabled = Column(Boolean, default=False)

    remember_token = Column(String(100), nullable=True)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)