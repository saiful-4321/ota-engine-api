import uuid
from sqlalchemy import Column, Boolean, String, ForeignKey, BigInteger, DateTime
from databases.database import OtaDbBase
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime

class Users(OtaDbBase):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    name = Column(String(155), nullable=False)
    username = Column(String(20), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True)
    mobile = Column(String(15), nullable=True)
    password = Column(String(255), nullable=False)
    access_token = Column(String(255), nullable=True, unique=True)
    status = Column(Boolean, nullable=False, default=True)
    user_role = Column(String(20), nullable=False, default="user")
    entity_type = Column(String(20), nullable=True, default="admin")
    entity_id = Column(String(20), nullable=True)
    last_login = Column(DateTime, nullable=True)
    last_logged_ip = Column(String(45), nullable=True)
    is_2fa_enabled = Column(Boolean, nullable=False, default=False)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True, default=None)

    creator = relationship("Users", remote_side=[id], foreign_keys=[created_by])
    updater = relationship("Users", remote_side=[id], foreign_keys=[updated_by])