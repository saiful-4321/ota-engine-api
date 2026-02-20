from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from databases.database import OtaDbBase
class CallbackApiLog(OtaDbBase):
    __tablename__ = "callback_api_logs"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)  # e.g., "backoffice", "oms"
    log_source = Column(String(50), nullable=False)  # e.g., "backoffice", "oms"
    request_body = Column(JSON, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_message = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    additional_info = Column(JSON, nullable=True)  # holds trx info etc.
