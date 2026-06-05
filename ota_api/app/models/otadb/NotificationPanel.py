import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, text
from sqlalchemy.orm import relationship
from databases.database import OtaDbBase

# qtraderdb
class NotificationPanel(OtaDbBase):
    __tablename__ = "notification_panel"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    sender = Column(String)
    receiver = Column(String)
    title = Column(String)
    details = Column(String)
    status = Column(String)
    response_link = Column(String)
    last_update = Column(DateTime(timezone=True), server_default=text('now()'))

    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'sender': self.sender,
            'receiver': self.receiver,
            'title': self.title,
            'details': self.details,
            'status': self.status,
            'response_link': self.response_link,
            'last_update': self.last_update.strftime('%I:%M:%S %p')
        }