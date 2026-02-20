from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from databases.database import OtaDbBase

class ActivityLog(OtaDbBase):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False)
    type = Column(String, nullable=False)
    details = Column(Text)
    platform = Column(String, default='WEB')
    created_at = Column(DateTime, default=datetime.utcnow)
