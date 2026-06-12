import uuid
from datetime import datetime
from sqlalchemy import Column, String, DECIMAL, NUMERIC, TIMESTAMP, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class Refund(OtaDbBase):
    __tablename__ = "refunds"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_id          = Column(BigInteger, ForeignKey("bookings.id"), nullable=False, index=True)
    ticket_id           = Column(BigInteger, ForeignKey("tickets.id"), nullable=False, index=True)
    
    refund_status       = Column(String(50), nullable=True)
    refund_amount       = Column(DECIMAL(12,2), nullable=True)
    airline_penalty     = Column(DECIMAL(12,2), nullable=True)
    service_charge      = Column(DECIMAL(12,2), nullable=True)
    supplier_reference  = Column(String(100), nullable=True)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at          = Column(TIMESTAMP, nullable=True)

    # Laravel-specific fields
    pcc                 = Column(String(20), nullable=True)
    cancellation_fee    = Column(DECIMAL(12,2), default=0.00, nullable=True)
    agent_penalty       = Column(DECIMAL(12,2), default=0.00, nullable=True)
    service_fee         = Column(DECIMAL(12,2), default=0.00, nullable=True)
    # currency tracking: all amounts stored in BDT
    # original_currency : ISO-4217 code the refund was processed in (e.g. 'USD')
    # conversion_rate   : 1 <original_currency> = <conversion_rate> BDT at refund time
    currency            = Column(String(3), default='BDT', nullable=True)
    original_currency   = Column(String(3), nullable=True, default='BDT', server_default='BDT')
    conversion_rate     = Column(NUMERIC(18, 6), nullable=True, default=1.0, server_default='1.000000')
    reason              = Column(String(255), nullable=True)
    status              = Column(String(255), nullable=True)
    actioned_by         = Column(BigInteger, nullable=True)
    remarks             = Column(String(255), nullable=True)

    # Dynamic alias properties
    @property
    def flight_booking_id(self):
        return self.booking_id

    @flight_booking_id.setter
    def flight_booking_id(self, value):
        self.booking_id = value

    @property
    def flight_ticket_id(self):
        return self.ticket_id

    @flight_ticket_id.setter
    def flight_ticket_id(self, value):
        self.ticket_id = value

    # Relationships
    booking = relationship("Booking")
    ticket  = relationship("Ticket")
