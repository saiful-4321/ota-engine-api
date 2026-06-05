import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, TIMESTAMP, ForeignKey, Enum, Date, BigInteger
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class BookingPassenger(OtaDbBase):
    __tablename__ = "booking_passengers"

    id                      = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                    = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id              = Column(BigInteger, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    
    passenger_type          = Column(Enum('ADT', 'CHD', 'INF', name='passenger_type_enum'), nullable=False)
    title                   = Column(String(20), nullable=True)
    first_name              = Column(String(100), nullable=False)
    last_name               = Column(String(100), nullable=False, index=True)
    gender                  = Column(String(10), nullable=True)
    date_of_birth           = Column(Date, nullable=True)
    nationality             = Column(String(2), nullable=True)
    passport_number         = Column(String(50), nullable=True, index=True)
    passport_expiry         = Column(Date, nullable=True)
    issuing_country         = Column(String(2), nullable=True)
    frequent_flyer_number   = Column(String(100), nullable=True)
    email                   = Column(String(255), nullable=True)
    phone                   = Column(String(50), nullable=True)
    created_at              = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    booking = relationship("Booking", back_populates="passengers")
    tickets = relationship("Ticket", back_populates="passenger")
