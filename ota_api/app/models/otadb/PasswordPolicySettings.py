from sqlalchemy import Column, Integer, String, Boolean, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from databases.database import OtaDbBase
from datetime import datetime


class PasswordPolicySettings(OtaDbBase):
    __tablename__ = "password_policy_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    password_strength = Column(String, default="normal")
    min_password_length = Column(Integer, default=5)
    reset_password_on_first_login = Column(Boolean, default=False)
    password_expiration_enabled = Column(Boolean, default=False)
    password_expiration_days = Column(Integer, nullable=True)
    two_factor_auth_enabled = Column(Boolean, default=False)
    two_factor_roles = Column(ARRAY(String), nullable=True)
    otp_sending_option = Column(
        String,
        CheckConstraint(
            "otp_sending_option IN ('mobile', 'email', 'both')",
            name="chk_otp_sending_option"
        ),
        nullable=True
    )
    updated_by = Column(String, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
