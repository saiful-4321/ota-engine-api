import uuid
from sqlalchemy import Column, Integer, String, DateTime, func, Text
from databases.database import OtaDbBase

class Announcement(OtaDbBase):
    __tablename__ = 'announcement'
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    user_role = Column(String, nullable=False)
    title = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # users = relationship('UserAnnouncementList', backref='announcement', lazy='joined')