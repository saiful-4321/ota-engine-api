import uuid
from sqlalchemy import * 
from sqlalchemy.sql import expression
from databases.database import OtaDbBase
from enum import Enum

class UserRoleEnum(Enum):
    ADMINISTRATOR = 'administrator'
    ADMIN = 'admin'
    EXEC = 'exec'
    IT = 'it'
    ASSOCIATE = 'associate'
    CLIENT = 'client'
class UserRoleNameEnum(Enum):
    ADMINISTRATOR = 'System Admin'
    ADMIN = 'Super Admin'
    EXEC = 'Executive'
    IT = 'IT'
    ASSOCIATE = 'Associate'
    CLIENT = 'Client'

class User(OtaDbBase):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    username = Column(String, index=True)
    password = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    photo = Column(String)
    users_roles = Column(String)
    acc_type = Column(String)
    user_id = Column(String)
    name = Column(String)
    email_status = Column(String)
    phone_status = Column(String)
    phone = Column(String)
    account_status = Column(String)
    max_login_web = Column(Integer, default=0, nullable=False)
    logged_in_web = Column(Integer, default=0, nullable=False)
    last_login = Column(String)
    login_ip = Column(String)
    first_login = Column(Boolean)  
    parking_enabled = Column(Boolean)  
    max_login_mobile = Column(Integer, default=0, nullable=False)
    logged_in_mobile = Column(Integer, default=0, nullable=False)
    total_max_login = Column(Integer, default=0, nullable=False)
    total_logged_in = Column(Integer, default=0, nullable=False)
    fcm_token = Column(String, nullable=True)
    is_tc_accepted = Column(Boolean, nullable=False, default=True, server_default=expression.true())
    is_2fa_enabled = Column(Boolean, default=True)