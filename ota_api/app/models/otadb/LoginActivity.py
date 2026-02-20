import uuid
from sqlalchemy import Column, Integer, String, TIMESTAMP, Date
from databases.database import OtaDbBase
from datetime import datetime

class LoginActivity(OtaDbBase):
    __tablename__ = 'login_activity'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    username = Column(String, index=True, nullable=False)
    user_role = Column(String, nullable=True)
    login_date = Column(TIMESTAMP)
    ip = Column(String, nullable=True)
    location = Column(String, nullable=True)
    browser = Column(String, nullable=True)
    os = Column(String, nullable=True)
    device = Column(String, nullable=True)
    attempt = Column(Integer, default=0)
    conn_number = Column(Integer, default=0)
    remarks = Column(String, nullable=True)
    date = Column(Date, nullable=False, default=datetime.utcnow)