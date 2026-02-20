from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from datetime import datetime
from databases.database import OtaDbBase

class APILog(OtaDbBase):
    __tablename__ = 'api_logs'

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    method = Column(String, index=True)
    url = Column(String)
    client_ip = Column(String)
    headers = Column(Text)
    query_params = Column(Text)
    request_body = Column(Text)
    user_agent = Column(String)
    response_status = Column(Integer)
    response_size = Column(Integer)
    response_body = Column(Text)
    process_time = Column(Float)
    raw_request_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(Text, nullable=True)
    username = Column(String)