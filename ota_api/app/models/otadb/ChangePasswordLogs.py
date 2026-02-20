from sqlalchemy import Column, Integer, String, DateTime, text
from databases.database import OtaDbBase


class ChangePasswordLogs(OtaDbBase):
    __tablename__ = "change_password_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    changed_by = Column(String(255), nullable=False)
    changed_at = Column(
        DateTime(timezone=True),
        server_default=text("now()")
    )
