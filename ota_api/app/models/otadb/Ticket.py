import uuid
from datetime import datetime
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, Enum, BigInteger, DECIMAL, NUMERIC, Integer
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class Ticket(OtaDbBase):
    __tablename__ = "tickets"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id          = Column(BigInteger, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    passenger_id        = Column(BigInteger, ForeignKey("booking_passengers.id"), nullable=False, index=True)
    
    ticket_number       = Column(String(20), nullable=False, unique=True, index=True)
    pnr                 = Column(String(20), nullable=True, index=True)
    fare_basis          = Column(String(50), nullable=True)
    ticket_status       = Column(Enum(
                            'ISSUED',
                            'VOID',
                            'REFUNDED',
                            'EXCHANGED',
                            name='ticket_status_enum'
                        ), nullable=False, default='ISSUED')
    
    validating_carrier  = Column(String(2), nullable=True)
    supplier_ticket_id  = Column(String(100), nullable=True)
    issue_date          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at          = Column(TIMESTAMP, nullable=True)

    # Laravel-specific fields
    ticket_no           = Column(String(255), nullable=True, unique=True)
    user_id             = Column(BigInteger, nullable=True)
    assigned_to         = Column(BigInteger, nullable=True)
    category_id         = Column(BigInteger, nullable=True)
    subject             = Column(String(255), nullable=True)
    priority            = Column(String(255), default='medium', nullable=True)
    status              = Column(String(255), default='open', nullable=True)
    last_reply_at       = Column(TIMESTAMP, nullable=True)
    created_by          = Column(BigInteger, nullable=True)
    updated_by          = Column(BigInteger, nullable=True)
    issuing_agent_id    = Column(String(255), nullable=True)
    ticketing_pcc       = Column(String(20), nullable=True)
    currency_id         = Column(BigInteger, nullable=True)
    # currency tracking: all amounts stored in BDT
    # search_currency : ISO-4217 code the ticket was priced in (e.g. 'USD')
    # conversion_rate : 1 <search_currency> = <conversion_rate> BDT at issue time
    search_currency     = Column(String(3), nullable=True, default='BDT', server_default='BDT')
    conversion_rate     = Column(NUMERIC(18, 6), nullable=True, default=1.0, server_default='1.000000')
    base_fare           = Column(DECIMAL(12,2), default=0.00, nullable=True)
    supplier_cost       = Column(DECIMAL(12,2), default=0.00, nullable=True)
    markup_amount       = Column(DECIMAL(12,2), default=0.00, nullable=True)
    discount_amount     = Column(DECIMAL(12,2), default=0.00, nullable=True)
    tax_amount          = Column(DECIMAL(12,2), default=0.00, nullable=True)
    ait_amount          = Column(DECIMAL(12,2), default=0.00, nullable=True)
    other_charges       = Column(DECIMAL(12,2), default=0.00, nullable=True)
    total_amount        = Column(DECIMAL(12,2), default=0.00, nullable=True)
    commission_amount   = Column(DECIMAL(12,2), default=0.00, nullable=True)
    tour_code           = Column(String(255), nullable=True)

    # Dynamic alias properties
    @property
    def flight_booking_id(self):
        return self.booking_id

    @flight_booking_id.setter
    def flight_booking_id(self, value):
        self.booking_id = value

    @property
    def flight_passenger_id(self):
        return self.passenger_id

    @flight_passenger_id.setter
    def flight_passenger_id(self, value):
        self.passenger_id = value

    # Relationships
    booking   = relationship("Booking", back_populates="tickets")
    passenger = relationship("BookingPassenger", back_populates="tickets")
