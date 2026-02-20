# models.User.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, text, ForeignKey
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

# qtraderdb
class UserAnnouncementList(OtaDbBase):
    __tablename__ = 'user_announcement_list'
    announcement_id = Column(Integer, ForeignKey('announcement.id'), primary_key=True)
    username = Column(String, default='ALL', primary_key=True, nullable=False)