from datetime import datetime, date
from typing import Optional, List, Dict
import ipaddress

from pydantic import BaseModel, Field, constr, conint, validator, EmailStr
from app.models.enums import (
    UserDevices, FileType
)

class UserSchema(BaseModel):
    name: constr(max_length=155)
    username: constr(max_length=20)
    email: EmailStr
    mobile: Optional[constr(max_length=15)] = None
    password: Optional[constr(max_length=255)] = None
    user_role: constr(max_length=20) = "user"
    entity_type: Optional[constr(max_length=20)] = None
    entity_id: Optional[constr(max_length=20)] = None
    status: bool = True
    
    class Config:
        orm_mode = True

# Base Model schemas

class IPWhitelistSchema(BaseModel):
    id: Optional[int] = None
    ip_address: str
    entity_type: str
    entity_id: int
    description: Optional[str] = None
    is_active: bool = True
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @validator('ip_address')
    def validate_ip_address(cls, value: str):
        try:
            ipaddress.ip_address(value)
        except ValueError:
            raise ValueError('Invalid IP address')
        return value
    
    @validator('entity_type')
    def validate_entity_type(cls, value: str):
        if value not in ['user', 'admin']:
            raise ValueError('Invalid entity type')
        return value

    class Config:
        orm_mode = True


class RolePermissionUpdate(BaseModel):
    permissions: List[str] = Field(
        ...,
        description="List of permissions to assign to the role"
    )

class UsernamePasswordBase(BaseModel):
    username: constr(min_length=1, max_length=30, strip_whitespace=True) #type: ignore
    password: constr(min_length=3, max_length=30, strip_whitespace=True) #type: ignore

#Auth schemas
class Login(UsernamePasswordBase):
    user_device: UserDevices = UserDevices.MOBILE

class ForgotPasswordRequest(BaseModel):
    username: constr(min_length=1, max_length=30, strip_whitespace=True) #type: ignore

class LogoutSchema(BaseModel):
    isLogoutByEvent: Optional[conint(ge=0, le=1)] = 0

class VerifyOtpRequest(BaseModel):
    username: constr(min_length=1, max_length=30, strip_whitespace=True) #type: ignore
    otp: int
    info_token: Optional[str]

class Verify2FAOtpRequest(BaseModel):
    otp: int
    info_token: str

class User2FASetting(BaseModel):
    setting_2fa: bool

class ResetForgetPasswordRequest(BaseModel):
    confirm_password: constr(min_length=3, max_length=30, strip_whitespace=True) #type: ignore


class UserQueryParams(BaseModel):
    user_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    file_type: FileType

class SignupSchema(BaseModel):
    client_code: constr(min_length=1, max_length=10, strip_whitespace=True) #type: ignore
    is_tc_accepted: int=1


class SignupConfirmSchema(BaseModel):
    client_code: constr(min_length=1, max_length=10, strip_whitespace=True) #type: ignore
    otp: constr(min_length=4, max_length=8, strip_whitespace=True) #type: ignore