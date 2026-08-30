from datetime import datetime
from sqlalchemy import Column, String, BigInteger, TIMESTAMP, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class AtBookingStatusHistory(OtaDbBase):
    __tablename__ = "at_booking_status_history"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    booking_id  = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    
    old_status  = Column(String(50), nullable=True)
    new_status  = Column(String(50), nullable=True)
    
    remarks     = Column(Text, nullable=True)
    changed_by  = Column(String(36), nullable=True) # UUID of user who changed status
    created_at  = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    booking = relationship("AtBooking", back_populates="history")
