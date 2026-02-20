# models.User.py
from sqlalchemy import Column, Integer, String, Boolean
from databases.database import OtaDbBase

# qtraderdb
class UserSetting(OtaDbBase):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(length=255))
    sms_status = Column(Boolean)
    email_status = Column(Boolean)
    dark_mode = Column(Boolean)
    otp = Column(String(length=5))
    mobile_ticker = Column(Boolean)
    mobile_index = Column(Boolean)
    mobile_clock = Column(Boolean)
    mobile_bo_info = Column(Boolean)
    username = Column(String)