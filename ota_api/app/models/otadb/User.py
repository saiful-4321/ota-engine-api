# models.User.py
from sqlalchemy import * 
from sqlalchemy.sql import expression
from databases.database import OtaDbBase
from enum import Enum

class UserRoleEnum(Enum):
    ADMINISTRATOR = 'administrator'
    BROKERADMIN = 'brokeradmin'
    BROKEREXEC = 'brokerexec'
    BROKERTRADER = 'brokertrader'
    BROKERCCD = 'brokerccd'
    BROKERIT = 'brokerit'
    ASSOCIATE = 'associate'
    CLIENT = 'client'
class UserRoleNameEnum(Enum):
    ADMINISTRATOR = 'System Admin'
    BROKERADMIN = 'Super Admin'
    BROKEREXEC = 'Executive'
    BROKERTRADER = 'Dealer'
    BROKERCCD = 'CCD'
    BROKERIT = 'IT'
    ASSOCIATE = 'Associate'
    CLIENT = 'Client'

class User(OtaDbBase):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
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
    exchange = Column(String)
    max_login = Column(Integer, default=0, nullable=False)
    logged_in = Column(Integer, default=0, nullable=False)
    last_login = Column(String)
    login_ip = Column(String)
    premium = Column(Boolean)  
    first_login = Column(Boolean)  
    parking_enabled = Column(Boolean)  
    is_bulk_order = Column(Boolean)  
    premium_start_date = Column(String)
    premium_end_date = Column(String)
    max_login_mobile = Column(Integer, default=0, nullable=False)
    logged_in_mobile = Column(Integer, default=0, nullable=False)
    total_max_login = Column(Integer, default=0, nullable=False)
    total_logged_in = Column(Integer, default=0, nullable=False)
    fcm_token = Column(String, nullable=True)
    is_tc_accepted = Column(Boolean, nullable=False, default=True, server_default=expression.true())
    is_2fa_enabled = Column(Boolean, default=True)