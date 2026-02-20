# services.otp.py

from random import randint
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Union
from ..models.otadb.User import User as UserModel
from ..models.otadb.Otp import Otp as OtpModel, OtpStatus
from random import randint
from config import DAILY_MAX_OTP, OTP_EXPIRES_TIME, RESEND_OTP_TIME
from sqlalchemy import cast, Date, DateTime
from ..services import *
from app.helpers.constants import BD_TIMEZONE

class OTPMixin:
    def otp_limit(self, user_id: int) -> bool:
        otp_count = 0
        limit = True
        
        if user_id:
            # otp_count = self.db.query(OtpModel).filter(OtpModel.user_id == user_id, OtpModel.created_at >= datetime.now().date()).count()
            otp_count = (
                self.db.query(OtpModel)
                .filter(
                    OtpModel.user_id == user_id,
                    cast(OtpModel.created_at, Date) >= datetime.now().date()
                )
                .count()
            )
        if otp_count >= DAILY_MAX_OTP:
            limit = False
        return limit
    
    def otp_limit_by_username(self, username: str) -> bool:
        otp_count = 0
        limit = True
        
        if username:
            otp_count = (
                self.db.query(OtpModel)
                .filter(
                    OtpModel.username == username,
                    cast(OtpModel.created_at, Date) >= datetime.now().date()
                )
                .count()
            )
        if otp_count >= DAILY_MAX_OTP:
            limit = False
        return limit
    
    def create_otp(self, user):
        if user.id:
            existing_otp = self.active_otp(user.id)
            if existing_otp:
                existing_otp.expires_at = datetime.now() + timedelta(minutes=OTP_EXPIRES_TIME)
                self.db.commit()
                self.db.refresh(existing_otp)
                return {'status': 409, 'otp': existing_otp.otp}
            if not self.otp_limit(user.id):
                return {'status': 422, 'message': MAX_OTP_LIMIT}
        
        elif not user.id and user.username:
            existing_otp = self.active_otp_by_username(user.username)
            if existing_otp:
                existing_otp.expires_at = datetime.now() + timedelta(minutes=OTP_EXPIRES_TIME)
                self.db.commit()
                self.db.refresh(existing_otp)
                return {'status': 409, 'otp': existing_otp.otp}
            if not self.otp_limit_by_username(user.username):
                return {'status': 422, 'message': MAX_OTP_LIMIT}
    
        otp = randint(10000, 99999)
        data = OtpModel(username=user.username, user_id=user.id, email=user.email, phone=user.phone, otp=otp, expires_at=datetime.now() + timedelta(minutes=OTP_EXPIRES_TIME))
        self.db.add(data)
        self.db.commit()
        self.db.refresh(data)
        
        return {'status': 201, 'otp': otp}
    
    def active_otp(self, user_id: int):
        return self.db.query(OtpModel).filter(OtpModel.user_id == user_id, OtpModel.status == OtpStatus.Pending, cast(OtpModel.expires_at, DateTime) >= datetime.now()).order_by(OtpModel.id.desc()).first()
    
    def active_otp_by_username(self, username: int):
        return self.db.query(OtpModel).filter(OtpModel.username == username, OtpModel.status == OtpStatus.Pending, cast(OtpModel.expires_at, DateTime) >= datetime.now()).order_by(OtpModel.id.desc()).first()
    
    def check_otp_validity(self, otp, user_id: int):
        return self.db.query(OtpModel).filter(OtpModel.otp == otp, OtpModel.user_id == user_id, OtpModel.status == OtpStatus.Pending, cast(OtpModel.expires_at, DateTime) >= datetime.now()).order_by(OtpModel.id.desc()).first()
    
    def check_otp_validity_by_username(self, otp, username: int):
        return self.db.query(OtpModel).filter(OtpModel.otp == otp, OtpModel.username == username, OtpModel.status == OtpStatus.Pending, cast(OtpModel.expires_at, DateTime) >= datetime.now()).order_by(OtpModel.id.desc()).first()
    
    def check_verified_otp_validity(self, user_id: int):
        return self.db.query(OtpModel).filter(OtpModel.user_id == user_id, OtpModel.status == OtpStatus.Verified, cast(OtpModel.expires_at, DateTime) >= datetime.now()).order_by(OtpModel.id.desc()).first()        
    
    def can_regenerate_otp(self, user_id: int):
        otp = self.db.query(OtpModel).filter(OtpModel.user_id == user_id).order_by(OtpModel.id.desc()).first()
        if not otp:
            return False
        # converting datetime string to datetime
        otp_created_at_datetime = otp.created_at
        valid_otp_datetime = otp_created_at_datetime + timedelta(seconds=RESEND_OTP_TIME)

        # otp_expires_at_datetime = otp.expires_at
        # now = datetime.now(BD_TIMEZONE)
        # if otp_created_at_datetime <= valid_otp_datetime and otp_expires_at_datetime > now:
        if otp_created_at_datetime <= valid_otp_datetime:
            return True
        else:
            return False

class OTPFunctions(OTPMixin):
    def __init__(self, db):
        self.db = db
