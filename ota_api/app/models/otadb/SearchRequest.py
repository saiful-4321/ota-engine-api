import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Date, TIMESTAMP, JSON
from databases.database import OtaDbBase


class SearchRequest(OtaDbBase):
    __tablename__ = "flight_search_requests_log"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    search_id        = Column(String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id          = Column(String(36), nullable=True,  index=True)
    session_id       = Column(String(100), nullable=True)

    supplier         = Column(String(20), nullable=False, default="sabre")

    trip_type        = Column(String(20), nullable=False)          # ONE_WAY | ROUND_TRIP
    cabin_class      = Column(String(20), nullable=False)          # Y | C | F

    adults           = Column(Integer, nullable=False, default=1)
    children         = Column(Integer, nullable=False, default=0)
    infants          = Column(Integer, nullable=False, default=0)

    origin           = Column(String(3), nullable=False, index=True)
    destination      = Column(String(3), nullable=False, index=True)

    departure_date   = Column(Date, nullable=False)
    return_date      = Column(Date, nullable=True)

    currency         = Column(String(3), nullable=False, default="BDT")

    result_count     = Column(Integer, nullable=True)   # flights returned
    request_metadata = Column(JSON, nullable=True)      # {supplier_response_time_ms, api_response_time_ms, ip_address, user_agent, ...}
    status           = Column(String(20), nullable=False, default="success")  # success | error

    created_at   = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
