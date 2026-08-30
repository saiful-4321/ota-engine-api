import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, TIMESTAMP, ForeignKey, Enum, Date, BigInteger
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class AtBookingPassenger(OtaDbBase):
    """
    Represents one traveller within a booking. Carries identity, travel
    documents, and contact information.

    passenger_type values: ADT (Adult), CHD (Child 2-11),
                           INF (Infant 0-1), INS (Infant with Seat)
    """
    __tablename__ = "at_booking_passengers"

    id                      = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                    = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id              = Column(BigInteger, ForeignKey("at_bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Passenger classification
    type                    = Column(String(10), nullable=False, default='ADT')  # ADT|CHD|INF|INS
    is_lead                 = Column(Integer, default=0, nullable=True)          # 1 = lead passenger
    title                   = Column(String(20), nullable=True)                  # MR|MRS|MS|MSTR|MISS
    first_name              = Column(String(100), nullable=False)
    last_name               = Column(String(100), nullable=False, index=True)
    gender                  = Column(String(10), nullable=True)                  # M|F
    dob                     = Column(Date, nullable=True)
    nationality             = Column(String(2), nullable=True)                   # ISO 3166-1 alpha-2

    # Travel documents
    passport_no             = Column(String(50), nullable=True, index=True)
    passport_expiry         = Column(Date, nullable=True)
    issuing_country         = Column(String(2), nullable=True)
    passport_issuing_country = Column(String(2), nullable=True)                  # Legacy alias

    # Loyalty
    frequent_flyer_airline  = Column(String(255), nullable=True)
    frequent_flyer_number   = Column(String(100), nullable=True)

    # Contact
    email                   = Column(String(255), nullable=True)
    phone                   = Column(String(50), nullable=True)

    created_at              = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at              = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at              = Column(TIMESTAMP, nullable=True)

    # Legacy fields (kept for Laravel backoffice compatibility)
    traveller_id            = Column(BigInteger, nullable=True, index=True)
    linked_passenger_id     = Column(BigInteger, nullable=True, index=True)
    passenger_type          = Column(String(10), nullable=True) # Legacy alias for type
    date_of_birth           = Column(Date, nullable=True)       # Legacy alias for dob

    # Dynamic alias property (legacy)
    @property
    def flight_booking_id(self):
        return self.booking_id

    @flight_booking_id.setter
    def flight_booking_id(self, value):
        self.booking_id = value

    # Relationships
    booking = relationship("AtBooking", back_populates="passengers")
    tickets = relationship("AtFlightTicket", back_populates="passenger")
