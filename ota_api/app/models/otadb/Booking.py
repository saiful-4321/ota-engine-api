import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DECIMAL, NUMERIC, TIMESTAMP, ForeignKey, Enum, BigInteger, text
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

class Booking(OtaDbBase):
    __tablename__ = "bookings"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid                = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    booking_reference   = Column(String(20), nullable=False, unique=True, index=True)
    user_id             = Column(String(36), nullable=False, index=True)
    supplier_id         = Column(BigInteger, ForeignKey("suppliers.id"), nullable=True, index=True)

    booking_status      = Column(Enum(
                            'PENDING',
                            'HOLD',
                            'CONFIRMED',
                            'TICKETED',
                            'CANCELLED',
                            'FAILED',
                            'EXPIRED',
                            name='booking_status_enum'
                        ), nullable=False, default='PENDING', index=True)

    payment_status      = Column(Enum(
                            'PENDING',
                            'PAID',
                            'FAILED',
                            'REFUNDED',
                            'PARTIAL_REFUND',
                            name='payment_status_enum'
                        ), nullable=False, default='PENDING')

    pnr                 = Column(String(20), nullable=True, index=True)
    supplier_booking_id = Column(String(100), nullable=True)
    # currency always stores 'BDT' — all amounts are persisted in BDT.
    # search_currency  : the ISO-4217 code the user searched / priced in (e.g. 'USD')
    # conversion_rate  : 1 <search_currency> = <conversion_rate> BDT at booking time
    currency            = Column(String(3), nullable=False, default='BDT', server_default='BDT')
    search_currency     = Column(String(3), nullable=True,  default='BDT', server_default='BDT')
    conversion_rate     = Column(NUMERIC(18, 6), nullable=True, default=1.0, server_default='1.000000')

    # All monetary amounts stored in BDT
    base_fare           = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')
    tax_amount          = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')
    service_fee         = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')
    discount_amount     = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')
    total_amount        = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')

    booking_expiry      = Column(TIMESTAMP, nullable=True, server_default=text("'1970-01-01 00:00:00'"))
    issued_at           = Column(TIMESTAMP, nullable=True)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at          = Column(TIMESTAMP, nullable=True)

    # Laravel-specific fields
    code                = Column(String(255), nullable=True, unique=True)
    pnr_code            = Column(String(255), nullable=True, index=True)
    airline_pnr         = Column(String(10), nullable=True)
    gds_source          = Column(String(255), nullable=True)
    airline_code        = Column(String(3), nullable=True)
    access_type         = Column(String(255), default='public', nullable=True)
    pcc                 = Column(String(20), nullable=True)
    office_id           = Column(String(50), nullable=True)
    status              = Column(String(255), nullable=True)
    journey_type        = Column(String(255), nullable=True)
    is_domestic         = Column(Integer, default=0, nullable=True)  # maps to boolean
    booking_date        = Column(TIMESTAMP, nullable=True)
    ticketing_time_limit = Column(TIMESTAMP, nullable=True)
    currency_id         = Column(BigInteger, nullable=True)
    other_charges       = Column(DECIMAL(12,2), default=0.00, nullable=True)
    commission_amount   = Column(DECIMAL(12,2), default=0.00, nullable=True)
    created_by          = Column(BigInteger, nullable=True)
    updated_by          = Column(BigInteger, nullable=True)

    # Relationships
    supplier   = relationship("Supplier")
    segments   = relationship("BookingSegment", back_populates="booking", cascade="all, delete-orphan")
    passengers = relationship("BookingPassenger", back_populates="booking", cascade="all, delete-orphan")
    tickets    = relationship("Ticket", back_populates="booking")
    payments   = relationship("Payment", back_populates="booking")
    history    = relationship("BookingStatusHistory", back_populates="booking")
