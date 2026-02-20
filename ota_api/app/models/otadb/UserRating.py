# models.User.py
from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime
from databases.database import OtaDbBase

# qtraderdb
class UserRating(OtaDbBase):
    __tablename__ = "user_ratings"

    id = Column(Integer, primary_key=True)
    rating = Column(Float)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    