from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from sqlalchemy.sql import func
from databases.database import OtaDbBase
from app.helpers.constants import BD_TIMEZONE

class UserNotificationSettings(OtaDbBase):
    __tablename__ = "user_notification_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, index=True, nullable=False)
    settings = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.now(BD_TIMEZONE))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
