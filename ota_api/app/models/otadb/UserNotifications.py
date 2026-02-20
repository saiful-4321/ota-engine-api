# models.User.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, text, ForeignKey
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

# qtraderdb
class UserNotifications(OtaDbBase):
    __tablename__ = "user_notifications"

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    notification_id = Column(Integer, ForeignKey('notification_panel.id'), primary_key=True)
    read = Column(Boolean, default=False)