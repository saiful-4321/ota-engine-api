from datetime import datetime
from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from databases.database import OtaDbBase

class ExportDownloadManager(OtaDbBase):
    __tablename__ = "export_download_manager"

    id = Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    title = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    url = Column(String, nullable=True)          
    remarks = Column(String, nullable=True)      
    status = Column(String, nullable=False, default='pending')
    type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True, default=None)  