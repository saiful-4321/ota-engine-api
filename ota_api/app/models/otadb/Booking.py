import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DECIMAL, TIMESTAMP, ForeignKey, Enum, BigInteger, text
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
    currency            = Column(String(3), nullable=False)

    base_fare           = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')
    tax_amount          = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')
    service_fee         = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')
    discount_amount     = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')
    total_amount        = Column(DECIMAL(12,2), nullable=False, default=0.00, server_default='0.00')

    booking_expiry      = Column(TIMESTAMP, nullable=True, server_default=text("'1970-01-01 00:00:00'"))
    issued_at           = Column(TIMESTAMP, nullable=True)
    created_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    supplier   = relationship("Supplier")
    segments   = relationship("BookingSegment", back_populates="booking", cascade="all, delete-orphan")
    passengers = relationship("BookingPassenger", back_populates="booking", cascade="all, delete-orphan")
    tickets    = relationship("Ticket", back_populates="booking")
    payments   = relationship("Payment", back_populates="booking")
    history    = relationship("BookingStatusHistory", back_populates="booking")
