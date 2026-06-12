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
    updated_at              = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at              = Column(TIMESTAMP, nullable=True)

    # Laravel-specific fields
    traveller_id            = Column(BigInteger, nullable=True, index=True)
    is_lead                 = Column(Integer, default=0, nullable=True)  # maps to boolean
    type                    = Column(String(255), nullable=True)
    linked_passenger_id     = Column(BigInteger, nullable=True, index=True)
    passport_issuing_country = Column(String(2), nullable=True)
    frequent_flyer_airline  = Column(String(255), nullable=True)
    dob                     = Column(Date, nullable=True)

    # Dynamic alias property
    @property
    def flight_booking_id(self):
        return self.booking_id

    @flight_booking_id.setter
    def flight_booking_id(self, value):
        self.booking_id = value

    # Relationships
    booking = relationship("Booking", back_populates="passengers")
    tickets = relationship("Ticket", back_populates="passenger")
