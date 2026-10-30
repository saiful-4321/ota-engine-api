"""
app/helpers/authentication.py

Authentication for the /auth endpoints, in two parts:
  1. Primitives — token creation/validation, login limits, FCM and session-token clean-up.
  2. Endpoint workflows — login (with optional 2FA), session clean-up, token refresh and the
     forgot-password OTP flow. Each returns the response body; AuthController only forwards it.
"""

from jose import JWTError, jwt
from sqlalchemy import func
from app.helpers.common import *
from datetime import datetime, timedelta
from app.utils.password_utils import verify_password, hash_password
from app.utils.formatting import format_date
from app.utils.request_utils import get_client_ip
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from app.models.otadb.User import User as UserModel, UserRoleEnum
from app.models.otadb.PasswordPolicySettings import PasswordPolicySettings
from config import JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_MINUTES, BASIC_AUTH_TOKEN, REDIS_DB, REDIS_AUTH_WEB_DB
from app.helpers.constants import *
from app.services.login_activity import login_activity
from app.utils.mqtt_utils import mqtt_service
from app.utils.redis_utils import redis_helper
from app.models.enums import AllowedDeviceType, UserDevices
from app.models.otadb.UserToken import UserToken, UserTokenStatus, UserTokenType
from redis import RedisError
import random
import string
import time
import base64
import json
from typing import Optional

from fastapi import BackgroundTasks, status
from sqlalchemy.orm import Session

from app.helpers.password_policy import (
    password_policy_settings, two_factor_policy_settings, validate_2fa_contact_info, validate_password_policy,
)
from app.models.otadb.AppVersion import AppVersion
from app.models.otadb.ChangePasswordLogs import ChangePasswordLogs
from app.models.otadb.Otp import OtpStatus
from app.models.schemas import ForgotPasswordRequest, ResetForgetPasswordRequest, Verify2FAOtpRequest, VerifyOtpRequest
from app.services.mail import MailFunctions
from app.services.otp import OTPFunctions
from app.utils.masking import mask_email, mask_phone
from app.utils.sms_utils import send_sms
from config import IS_EMAIL_ENABLED, IS_SMS_ENABLED, OTP_EXPIRES_TIME, SECRET_2FA

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# async def token_validation(token: str = Depends(oauth2_scheme)):
async def token_validation(token, refresh_token: bool = False):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        if not refresh_token:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
        else:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            
        if not payload or type(payload) is not dict or payload.get("username") is None:
            return None

        token_data = {
            "id": payload.get("id"),
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "users_roles": payload.get("users_roles"),
            "acc_type": payload.get("acc_type"),
            "device_os": payload.get("device_os", "ANR"),
            "device": payload.get("device"),
            "device_id": payload.get("device_id")
        }
        
        cache_key = token
        try:
            if refresh_token:
                user_prev_token = otadb.query(UserToken.token, UserToken.device, UserToken.token_type).filter(UserToken.refresh_token == token, UserToken.status == UserTokenStatus.VALID).first()
                if user_prev_token:
                    token_val, device, token_type = user_prev_token
                    if device == UserDevices.DESKTOP and token_type == UserTokenType.SESSION:
                        redis_helper.delete_key(token_val, db=REDIS_AUTH_WEB_DB)
                    elif device == UserDevices.MOBILE and token_type == UserTokenType.JWT:
                        redis_helper.delete_key(token_val, db=REDIS_DB)
                    otadb.query(UserToken).filter(UserToken.refresh_token == token).filter(UserToken.status == UserTokenStatus.VALID).delete(synchronize_session=False)
                    otadb.commit()
                    return token_data
                return None

            if token_data["device"].lower() == UserDevices.MOBILE.value.lower():
                validtoken = redis_helper.get_data(cache_key, db=REDIS_DB)
            else:
                validtoken = redis_helper.get_data(cache_key, db=REDIS_AUTH_WEB_DB)
            if not validtoken:
                return None
            
        except RedisError as redis_ex:
            write_log(f"Redis error: {get_error_info(redis_ex)}", "token_validation()")
        
        try:
            if token_data["device"].lower() == UserDevices.MOBILE.value.lower():
                redis_helper.set_data_ttl(cache_key, token_data["username"], int(ACCESS_TOKEN_EXPIRE_MINUTES), db=REDIS_DB)
            else:
                redis_helper.set_data_ttl(cache_key, token_data["username"], int(ACCESS_TOKEN_EXPIRE_MINUTES), db=REDIS_AUTH_WEB_DB)
        except RedisError as redis_ex:
            write_log(f"Redis error@get_user_token: {get_error_info(redis_ex)}", "token_validation()")
        
        return token_data
    except JWTError:
        return None
    except Exception as e:
        write_log(get_error_info(e), "token_validation")
    finally:
        if otadb is not None:
            otadb.close()

async def validate_basic_token(token: str):
    try:
        if not token:
            return False
        if token != BASIC_AUTH_TOKEN:
            return False
        return True
    except Exception as e:
        write_log(get_error_info(e), "validate_sync_token")

async def validate_sync_token(token: str = Depends(oauth2_scheme)):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("username")
        if username is None:
            return None
        
        user_info = otadb.query(
            UserModel.id, UserModel.user_id, UserModel.username, UserModel.email, UserModel.account_status, UserModel.acc_type, UserModel.users_roles,
        ).filter(
            func.lower(UserModel.username) == username.lower()
        ).order_by(UserModel.id.asc()).first()

        if not user_info:
            return False
        
        user_dict = dict(user_info)
        user_roles = user_dict.get('users_roles')
        token_data = {
            "username": username, 
            "id": user_dict.get('id'), 
            "user_id": user_dict.get('user_id'), 
            "users_roles": user_roles, 
            "acc_type": user_dict.get('acc_type'), 
            "account_status": user_dict.get('account_status'),
        }
        
        return token_data
    except JWTError as jwt_error:
        return None
    except Exception as e:
        write_log(get_error_info(e), "validate_sync_token()")
    finally:
        if otadb is not None:
            otadb.close()
    
def authenticate_user(username: str, password: str, user: UserModel | None = None):
    db = None
    try:
        db = next(get_ota_db_session())
        
        if user is None:
            user = db.query(UserModel).filter(
                func.lower(UserModel.username) == username.lower()
            ).order_by(UserModel.id.asc()).first()

        if not user:
            return {"status": 404, "message": USER_NOT_FOUND}

        if user.account_status != "active":
            return {"status": 403, "message": INACTIVE_USER}

        allowed_roles = {
            UserRoleEnum.CLIENT.value,
            UserRoleEnum.ASSOCIATE.value,
            UserRoleEnum.ADMIN.value,
            UserRoleEnum.ADMINISTRATOR.value,
            UserRoleEnum.IT.value,
            UserRoleEnum.EXEC.value,
        }

        if user.users_roles not in allowed_roles:
            return {
                "status": 403,
                "message": f"Access denied: '{user.users_roles}' type user is not allowed."
            }

        if not verify_password(password, user.password):
            return {"status": 401, "message": INCORRECT_PASSWORD}

        return {"status": 200, "message": SUCCESS, "user": user}
    except Exception as e:
        write_log(get_error_info(e), "function: authenticate_user")
        return {"status": 500, "message": INTERNAL_SERVER_ERROR}
    finally:
        if db is not None:
            db.close()


async def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(BD_TIMEZONE) + expires_delta
    else:
        expire = datetime.now(BD_TIMEZONE) + timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def create_refresh_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(BD_TIMEZONE) + expires_delta
    else:
        expire = datetime.now(BD_TIMEZONE) + timedelta(minutes=int(REFRESH_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_refresh_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_refresh_jwt

async def get_user_token(user: UserModel, additionalInfo = None, token_only: bool = False):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        device_os_input = (additionalInfo.get('os') if additionalInfo else None) or 'ANR'
        device_name = (additionalInfo.get('device') if additionalInfo else None) or 'mobile'
        try:
            device_os = AllowedDeviceType(device_os_input).value
        except ValueError:
            device_os = AllowedDeviceType.ANR.value

        user_data = {key: getattr(user, key) for key in ["id", "user_id", "username", "name", "users_roles", "acc_type"]}  
        user_data["device_os"] = device_os
        user_data["device"] = device_name.lower()
        user_data["device_id"] = (additionalInfo.get('device_id') if additionalInfo else None)
        user_data['name'] = user.name if user.name else ""
        payload = {**user_data, "name": user.name}
        access_token = await create_access_token(data=payload)
        refresh_token = await create_refresh_token(data=payload)
        expires_at = datetime.now(BD_TIMEZONE) + timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
        try:
            if user_data["device"] == UserDevices.MOBILE.value.lower():
                redis_helper.set_data_ttl(access_token, user.username, int(ACCESS_TOKEN_EXPIRE_MINUTES), db=REDIS_DB)
            else:
                redis_helper.set_data_ttl(access_token, user.username, int(ACCESS_TOKEN_EXPIRE_MINUTES), db=REDIS_AUTH_WEB_DB)
        except RedisError as redis_ex:
            write_log(f"Redis error@get_user_token: {get_error_info(redis_ex)}", "get_user_token()")
            return None
        try:          
            user_token = UserToken(
                username=user.username,
                user_id=user.id,
                token=access_token,
                refresh_token=refresh_token,
                status=UserTokenStatus.VALID,
                expires_at=expires_at,
                device=UserDevices.MOBILE if device_name.lower() == UserDevices.MOBILE.value.lower() else UserDevices.DESKTOP,
                token_type=UserTokenType.JWT if additionalInfo and additionalInfo.get('device', '').lower() == UserDevices.MOBILE.value.lower() else UserTokenType.SESSION,
                agents=f"{device_os}-{additionalInfo.get('device_id') or ''}"
            ) 
            otadb.add(user_token)
            otadb.commit()        
        except Exception as e:
            write_log(f"DB error@get_user_token: {get_error_info(e)}", "get_user_token()")
            return None
        
        token_payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer"
        }

        if token_only:
            return token_payload

        return {
            **user_data,
            **token_payload
        }
    except Exception as e:
        otadb.rollback()
        write_log(get_error_info(e), 'get_user_token')
        return None
    finally:
        if otadb is not None:
            otadb.close()

def handle_login_limit(user: UserModel, request: Request = Depends(), activity=None):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        user = otadb.query(UserModel).filter(UserModel.id == user.id).first()
        if not user:
            return {'status': False, 'code': 404, 'message': USER_NOT_FOUND}

        device_type = activity['device'].lower()
        currentdate = format_date(datetime.now(BD_TIMEZONE), "%d/%m/%Y-%I:%M:%S %p")
        user.last_login = currentdate
        user.login_ip = get_client_ip(request)

        if device_type == UserDevices.MOBILE.value.lower():
            user.logged_in_mobile = (user.logged_in_mobile or 0) + 1
        else:
            user.logged_in_web = (user.logged_in_web or 0) + 1
        user.total_logged_in = user.logged_in_web + user.logged_in_mobile

        if (user.total_max_login or 0) <= 0:
            return {'status': False, 'code': 403, 'message': YOU_ARE_NOT_ALLOWED_TO_LOGIN_ANY_DEVICE}
        if activity['device'].lower() == UserDevices.MOBILE.value.lower() and (user.max_login_mobile or 0) <= 0:
            return {'status': False, 'code': 403, 'message': YOU_ARE_NOT_ALLOWED_TO_LOGIN_ANY_MOBILE_DEVICE}
        if activity['device'].lower() == UserDevices.DESKTOP.value.lower() and (user.max_login_web or 0) <= 0:
            return {'status': False, 'code': 403, 'message': YOU_ARE_NOT_ALLOWED_TO_LOGIN_ANY_DESKTOP_DEVICE}

        exceeded_web = user.logged_in_web > user.max_login_web
        exceeded_mobile = user.logged_in_mobile > user.max_login_mobile
        exceeded_total = user.total_logged_in > user.total_max_login

        if exceeded_web or exceeded_mobile or exceeded_total: 
            limit_notification = activity.get('limit_notification') if activity else None
            if limit_notification:
                login_activity(
                    user,
                    remarks=MAX_ALLOWED_LOGIN_EXTENDED_FOR_MOBILE if activity['device'].lower() == UserDevices.MOBILE.value.lower() else MAX_ALLOWED_LOGIN_EXTENDED,
                    activity=activity,
                    conn_number=user.logged_in_mobile if activity['device'].lower() == UserDevices.MOBILE.value.lower() else user.logged_in_web
                )
                if device_type == UserDevices.MOBILE.value.lower():
                    user.logged_in_mobile = (user.logged_in_mobile or 0) - 1
                else:
                    user.logged_in_web = (user.logged_in_web or 0) - 1
                user.total_logged_in = user.logged_in_web + user.logged_in_mobile
                otadb.commit()
                return {'status': False, 'code': 409, 'message': ACTIVE_SESSION_EXISTS}
            else:
                login_activity(
                    user,
                    remarks=MAX_ALLOWED_LOGIN_EXTENDED_FOR_MOBILE if activity['device'].lower() == UserDevices.MOBILE.value.lower() else MAX_ALLOWED_LOGIN_EXTENDED,
                    activity=activity,
                    conn_number=user.logged_in_mobile if activity['device'].lower() == UserDevices.MOBILE.value.lower() else user.logged_in_web
                )
                if exceeded_total:
                    result = remove_tokens(
                        username=user.username,
                        device='all'
                    )
                    if not result['status']:
                        return {'status': False, 'code': result['code'], 'message': result['message']}
                    if device_type == UserDevices.MOBILE.value.lower():
                        user.logged_in_mobile = (user.logged_in_mobile or 0) - 1
                        user.logged_in_web = 0
                    else:
                        user.logged_in_mobile = 0
                        user.logged_in_web = (user.logged_in_web or 0) - 1
                    user.total_logged_in = 1 
                elif exceeded_mobile:
                    result = remove_tokens(
                        username=user.username,
                        device=UserDevices.MOBILE
                    )
                    if not result['status']:
                        return {'status': False, 'code': result['code'], 'message': result['message']}
                    
                    user.logged_in_mobile = (user.logged_in_mobile or 0) - 1 
                    user.total_logged_in = user.logged_in_mobile + user.logged_in_web
                    
                elif exceeded_web:
                    result = remove_tokens(
                        username=user.username,
                        device=UserDevices.DESKTOP,
                    )
                    if not result['status']:
                        return {'status': False, 'code': result['code'], 'message': result['message']}
                    
                    user.logged_in_web = (user.logged_in_web or 0) - 1
                    user.total_logged_in = user.logged_in_mobile + user.logged_in_web

        otadb.commit()
        login_activity(
            user,
            remarks="Login",
            activity=activity,
            conn_number=user.logged_in_mobile if activity['device'].lower() == 'mobile' else user.logged_in_web
        )
        return {'status': True, 'code': 200, 'message': SUCCESS}
    except Exception as e:
        write_log(f"Error in handle_login_limit: {get_error_info(e)}", source="handle_login_limit")
        return {'status': False, 'code': 500, 'message': 'Internal server error'}
    finally:
        if otadb:
            otadb.close()

async def generate_random_password():
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        policy = otadb.query(PasswordPolicySettings).first()
        min_length = policy.min_password_length if policy and policy.min_password_length else 5
        strength = policy.password_strength if policy and policy.password_strength else "normal"
        letters = string.ascii_letters
        digits = string.digits
        special_chars = "!@#$%^&*()[]{}~`?"
        password_chars = []

        if strength == "alphanumeric":
            password_chars.append(random.choice(letters))
            password_chars.append(random.choice(digits))
            allowed_chars = letters + digits
        elif strength == "special_alphanumeric":
            password_chars.append(random.choice(letters))
            password_chars.append(random.choice(digits))
            password_chars.append(random.choice(special_chars))
            allowed_chars = letters + digits + special_chars
        else:  
            allowed_chars = letters + digits
            
        remaining_length = max(min_length - len(password_chars), 0)
        password_chars += [random.choice(allowed_chars) for _ in range(remaining_length)]
        random.shuffle(password_chars)

        return "".join(password_chars)
    except Exception as e:
        write_log(get_error_info(e), "generate_random_password")
        return None
    finally:
        if otadb is not None:
            otadb.close()


def register_fcm_token(username: str, fcm_token: str):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        user = otadb.query(UserModel).filter(func.lower(UserModel.username) == username.lower()).first()

        if not user:
            write_log(f"User not found for username: {username}", "register_fcm_token()")
            return {'status': False, 'code': 404, 'message': 'User not found'}
        
        # Clear this token from all other users
        otadb.query(UserModel).filter(
            UserModel.fcm_token == fcm_token,
            func.lower(UserModel.username) != username.lower()
        ).update({UserModel.fcm_token: None}, synchronize_session=False)

        if user.fcm_token == fcm_token:
            return {'status': True, 'code': 200, 'message': 'Token already registered'}

        user.fcm_token = fcm_token
        otadb.commit()

        return {'status': True, 'code': 200, 'message': 'Token registered successfully'}
    except Exception as e:
        if otadb:
            otadb.rollback()
        write_log(get_error_info(e), "register_fcm_token")
        return {'status': False, 'code': 500, 'message': 'Internal server error'}
    finally:
        if otadb:
            otadb.close()

def remove_tokens(username: str, device):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        if device == 'all':
            tokens = (
                    otadb.query(UserToken.token, UserToken.device, UserToken.token_type)
                    .filter(UserToken.username == username)
                    .filter(UserToken.status == UserTokenStatus.VALID)
                    .all()
                )
            tokens_web = []
            tokens_mobile = []
            for token_obj in tokens:  
                t = token_obj[0]  
                if token_obj.device == UserDevices.DESKTOP and token_obj.token_type == UserTokenType.SESSION:
                    tokens_web.append(t)
                elif token_obj.device == UserDevices.MOBILE and token_obj.token_type == UserTokenType.JWT:
                    tokens_mobile.append(t)
            try:
                redis_helper.delete_keys_pipeline([t for t in tokens_web], db=REDIS_AUTH_WEB_DB)
                redis_helper.delete_keys_pipeline([t for t in tokens_mobile], db=REDIS_DB)
            except RedisError as redis_ex:
                    write_log(f"Redis error@remove_tokens: {get_error_info(redis_ex)}", "remove_tokens")
                    return {'status': False, 'code': 500, 'message': INTERNAL_SERVER_ERROR_REDIS}
            otadb.query(UserToken).filter(UserToken.username == username) \
                                .filter(UserToken.status == UserTokenStatus.VALID) \
                                .delete(synchronize_session=False)   # as the token records are not used anywhere else so the updated value is not needed immediately
            mqtt_service.publish('logout_user', json.dumps({
                    'user_name': username,
                    'logout': 'true',
                    'device': 'ALL'
                }))
        
        elif device == UserDevices.DESKTOP:
            tokens = (
                otadb.query(UserToken.token)
                .filter(UserToken.username == username)
                .filter(UserToken.device == UserDevices.DESKTOP)
                .filter(UserToken.token_type == UserTokenType.SESSION)
                .filter(UserToken.status == UserTokenStatus.VALID)
                .all()
            )
            try:
                redis_helper.delete_keys_pipeline([t[0] for t in tokens], db=REDIS_AUTH_WEB_DB)
            except RedisError as redis_ex:
                    write_log(f"Redis error@remove_tokens: {get_error_info(redis_ex)}", "remove_tokens")
                    return {'status': False, 'code': 500, 'message': INTERNAL_SERVER_ERROR_REDIS}
            otadb.query(UserToken).filter(UserToken.username == username) \
                                .filter(UserToken.status == UserTokenStatus.VALID) \
                                .filter(UserToken.device == UserDevices.DESKTOP) \
                                .filter(UserToken.token_type == UserTokenType.SESSION) \
                                .delete(synchronize_session=False) 
            mqtt_service.publish('logout_user', json.dumps({
                    'user_name': username,
                    'logout': 'true',
                    'device': 'Desktop'
                }))
        elif device == UserDevices.MOBILE:
            tokens = (
                otadb.query(UserToken.token)
                .filter(UserToken.username == username)
                .filter(UserToken.device == UserDevices.MOBILE)
                .filter(UserToken.token_type == UserTokenType.JWT)
                .filter(UserToken.status == UserTokenStatus.VALID)
                .all()
            )
            try:
                redis_helper.delete_keys_pipeline([t[0] for t in tokens], db=REDIS_DB)
            except RedisError as redis_ex:
                    write_log(f"Redis error@remove_tokens: {get_error_info(redis_ex)}", "remove_tokens")
                    return {'status': False, 'code': 500, 'message': INTERNAL_SERVER_ERROR_REDIS}
            otadb.query(UserToken).filter(UserToken.username == username) \
                                .filter(UserToken.status == UserTokenStatus.VALID) \
                                .filter(UserToken.device == UserDevices.MOBILE) \
                                .filter(UserToken.token_type == UserTokenType.JWT) \
                                .delete(synchronize_session=False)
            mqtt_service.publish('logout_user', json.dumps({
                    'user_name': username,
                    'logout': 'true',
                    'device': 'Mobile'
                }))
        else:
            return {'status': False, 'code': 400, 'message': INVALID_DEVICE_TYPE}
        otadb.commit()
        return {'status': True, 'code': 200, 'message': 'Tokens removed successfully'}
    except Exception as e:
        if otadb:
            otadb.rollback()
        write_log(f"DB error@remove_tokens :{get_error_info(e)}", "remove_tokens")
        return {'status': False, 'code': 500, 'message': INTERNAL_SERVER_ERROR}
    finally:
        if otadb:
            otadb.close()

def remove_tokens_except_current(username: str, device: str, token: str, device_id=None):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        if device == 'all':
            tokens = (
                    otadb.query(UserToken.token, UserToken.device, UserToken.token_type)
                    .filter(UserToken.username == username)
                    .filter(UserToken.status == UserTokenStatus.VALID)
                    .filter(UserToken.token != token)
                    .all()
                )
            tokens_web = []
            tokens_mobile = []
            for token_obj in tokens:  
                t = token_obj[0]  
                if token_obj.device == UserDevices.DESKTOP and token_obj.token_type == UserTokenType.SESSION:
                    tokens_web.append(t)
                elif token_obj.device == UserDevices.MOBILE and token_obj.token_type == UserTokenType.JWT:
                    tokens_mobile.append(t)
            try:
                redis_helper.delete_keys_pipeline([t for t in tokens_web], db=REDIS_AUTH_WEB_DB)
                redis_helper.delete_keys_pipeline([t for t in tokens_mobile], db=REDIS_DB)
            except RedisError as redis_ex:
                    write_log(f"Redis error@remove_tokens_except_current: {get_error_info(redis_ex)}", "remove_tokens_except_current")
                    return {'status': False, 'code': 500, 'message': INTERNAL_SERVER_ERROR_REDIS}
            otadb.query(UserToken).filter(UserToken.username == username) \
                                .filter(UserToken.status == UserTokenStatus.VALID) \
                                .filter(UserToken.token != token) \
                                .delete(synchronize_session=False)   # as the token records are not used anywhere else so the updated value is not needed immediately
            mqtt_service.publish('logout_user', json.dumps({
                    'user_name': username,
                    'logout': 'true',
                    'device': 'ALL',
                    'device_id': device_id
                }))
        
        elif device == UserDevices.DESKTOP:
            tokens = (
                otadb.query(UserToken.token)
                .filter(UserToken.username == username)
                .filter(UserToken.device == UserDevices.DESKTOP)
                .filter(UserToken.token_type == UserTokenType.SESSION)
                .filter(UserToken.status == UserTokenStatus.VALID)
                .filter(UserToken.token != token)
                .all()
            )
            try:
                redis_helper.delete_keys_pipeline([t[0] for t in tokens], db=REDIS_AUTH_WEB_DB)
            except RedisError as redis_ex:
                    write_log(f"Redis error@remove_tokens_except_current: {get_error_info(redis_ex)}", "remove_tokens_except_current")
                    return {'status': False, 'code': 500, 'message': INTERNAL_SERVER_ERROR_REDIS}
            otadb.query(UserToken).filter(UserToken.username == username) \
                                .filter(UserToken.status == UserTokenStatus.VALID) \
                                .filter(UserToken.device == UserDevices.DESKTOP) \
                                .filter(UserToken.token_type == UserTokenType.SESSION) \
                                .filter(UserToken.token != token) \
                                .delete(synchronize_session=False) 
            mqtt_service.publish('logout_user', json.dumps({
                    'user_name': username,
                    'logout': 'true',
                    'device': 'Desktop',
                    'device_id': device_id
                }))
        elif device == UserDevices.MOBILE:
            tokens = (
                otadb.query(UserToken.token)
                .filter(UserToken.username == username)
                .filter(UserToken.device == UserDevices.MOBILE)
                .filter(UserToken.token_type == UserTokenType.JWT)
                .filter(UserToken.status == UserTokenStatus.VALID)
                .filter(UserToken.token != token)
                .all()
            )
            try:
                redis_helper.delete_keys_pipeline([t[0] for t in tokens], db=REDIS_DB)
            except RedisError as redis_ex:
                    write_log(f"Redis error@remove_tokens_except_current: {get_error_info(redis_ex)}", "remove_tokens_except_current")
                    return {'status': False, 'code': 500, 'message': INTERNAL_SERVER_ERROR_REDIS}
            otadb.query(UserToken).filter(UserToken.username == username) \
                                .filter(UserToken.status == UserTokenStatus.VALID) \
                                .filter(UserToken.device == UserDevices.MOBILE) \
                                .filter(UserToken.token_type == UserTokenType.JWT) \
                                .filter(UserToken.token != token) \
                                .delete(synchronize_session=False)
            mqtt_service.publish('logout_user', json.dumps({
                    'user_name': username,
                    'logout': 'true',
                    'device': 'Mobile',
                    'device_id': device_id
                }))
        else:
            return {'status': False, 'code': 400, 'message': INVALID_DEVICE_TYPE}
        otadb.commit()
        return {'status': True, 'code': 200, 'message': 'Tokens removed successfully'}
    except Exception as e:
        if otadb:
            otadb.rollback()
        write_log(get_error_info(e), "remove_tokens_except_current")
        return {'status': False, 'code': 500, 'message': INTERNAL_SERVER_ERROR}
    finally:
        if otadb:
            otadb.close()

# ═══════════════════════════════════════════════════════════════════════════
# Endpoint workflows (AuthController)
# ═══════════════════════════════════════════════════════════════════════════

OTP_SUBJECT = "One-Time Password (OTP)"
INVALID_INFO_TOKEN = "Invalid information token."
_PASSWORD_RESET_OTP_BODY = f"""
            Please use the following OTP to proceed with resetting your password.<br><br>
            This OTP is valid for the next <b>{OTP_EXPIRES_TIME}</b> minutes.<br><br>
            If you did not request a password reset, please ignore this message or contact our support team.
        """
_TWO_FACTOR_OTP_BODY = f"""
                        Please use the following OTP to proceed with two factor authentication.<br><br>
                        This OTP is valid for the next <b>{OTP_EXPIRES_TIME}</b> minutes.<br><br>"""


# ── Lookups ──────────────────────────────────────────────────────────────────

def _find_user(otadb: Session, username: str, active_only: bool = True, oldest_first: bool = False):
    query = otadb.query(UserModel).filter(func.lower(UserModel.username) == username.lower())
    if active_only:
        query = query.filter(UserModel.account_status == "active")
    if oldest_first:
        query = query.order_by(UserModel.id.asc())
    return query.first()


# ── 2FA information token ────────────────────────────────────────────────────
# The login context is carried between /login and /verify-2fa-otp in an XOR-obfuscated token.

def _xor(data: bytes) -> bytes:
    key_bytes = SECRET_2FA.encode("utf-8")
    return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))


def encode_info_token(activity: dict) -> str:
    json_bytes = json.dumps(activity, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return base64.b64encode(_xor(json_bytes)).decode('utf-8')


def decode_info_token(info_token: str) -> dict:
    return json.loads(_xor(base64.b64decode(info_token.encode("utf-8"))).decode("utf-8"))


# ── OTP delivery ─────────────────────────────────────────────────────────────

def _send_otp_email(background_tasks: BackgroundTasks, user, otp, body: str) -> None:
    button = {"text": "OTP: " + str(otp), "link": "#"}
    mail_functions = MailFunctions(recipient_email=user.email, subject=OTP_SUBJECT, body=body, userInfo=user, button=button)
    background_tasks.add_task(mail_functions.send_email)


def _two_factor_channel_error(otp_sending_option: str, user) -> Optional[str]:
    """Why the OTP cannot be delivered on the user's chosen channel, or None."""
    if not IS_EMAIL_ENABLED and not IS_SMS_ENABLED:
        return NO_EMAIL_SMS_SERVICE
    if otp_sending_option == 'email' and not IS_EMAIL_ENABLED:
        return TWO_FA_EMAIL_SERVICE_NOT_ENABLED if user.email else TWO_FA_EMAIL_SERVICE_NOT_ENABLED_FOUND
    if otp_sending_option == 'mobile' and not IS_SMS_ENABLED:
        return TWO_FA_SMS_SERVICE_NOT_ENABLED if user.phone else TWO_FA_SMS_SERVICE_NOT_ENABLED_FOUND
    has_error, message = validate_2fa_contact_info(otp_sending_option, user, IS_EMAIL_ENABLED, IS_SMS_ENABLED)
    return message if has_error else None


def _send_two_factor_otp(background_tasks: BackgroundTasks, user, otp, otp_sending_option: str) -> list:
    """Sends the 2FA OTP; returns the masked channels it went to."""
    sent_channels = []
    if otp_sending_option in ('both', 'email') and IS_EMAIL_ENABLED and user.email:
        sent_channels.append(mask_email(user.email))
        _send_otp_email(background_tasks, user, otp, _TWO_FACTOR_OTP_BODY)
    if otp_sending_option in ('both', 'mobile') and IS_SMS_ENABLED and user.phone:
        sent_channels.append(mask_phone(user.phone))
        send_sms({
            "phone": user.phone,
            "message": f"Please use the following otp for two factor authentication.\n OTP: {otp}",
        })
    return sent_channels


# ── Login ────────────────────────────────────────────────────────────────────

def build_login_activity(request: Request, device: str, device_id: Optional[str], os: Optional[str],
                         browser: Optional[str], location: Optional[str]) -> dict:
    return {
        "device": device,
        "os": os,
        "browser": browser,
        "location": location,
        "ip": request.client.host,
        "device_id": device_id,
        "limit_notification": True,
    }


async def _complete_login(user, request: Request, activity: dict, fcm_token: Optional[str],
                          background_tasks: BackgroundTasks) -> dict:
    """Issues the tokens once the user is authenticated (and 2FA passed), within the login limits."""
    if fcm_token:
        background_tasks.add_task(register_fcm_token, username=user.username, fcm_token=fcm_token)
    login_limit = handle_login_limit(user=user, request=request, activity=activity)
    if login_limit['status'] != True:
        return common_response(login_limit['code'], login_limit['message'])
    response = await get_user_token(user=user, additionalInfo=activity)
    response.update(await password_policy_settings(user))
    return common_response(status.HTTP_200_OK, SUCCESS, response)


def _two_factor_challenge(user, activity: dict, fcm_token: Optional[str], two_factor_response: dict,
                          background_tasks: BackgroundTasks, otadb: Session) -> dict:
    """Sends the 2FA OTP and answers 206 with the info_token needed by /verify-2fa-otp."""
    two_factor_response.pop('two_factor_auth_enabled')
    otp_sending_option = two_factor_response.pop('otp_sending_option')
    activity['username'] = user.username
    activity['fcm_token'] = fcm_token
    two_factor_response['info_token'] = encode_info_token(activity)

    channel_error = _two_factor_channel_error(otp_sending_option, user)
    if channel_error:
        return common_response(status.HTTP_400_BAD_REQUEST, channel_error, two_factor_response)

    otp_result = OTPFunctions(otadb).create_otp(user)
    if otp_result['status'] not in (201, 409):
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, otp_result['message'], two_factor_response)

    sent_channels = _send_two_factor_otp(background_tasks, user, otp_result['otp'], otp_sending_option)
    if not sent_channels:
        message = "Two factor authentication is enabled, but no valid delivery channel is available."
        return common_response(status.HTTP_400_BAD_REQUEST, message, two_factor_response)
    message = "An OTP was sent to your " + " and ".join(sent_channels) + "."
    return common_response(status.HTTP_206_PARTIAL_CONTENT, message, two_factor_response)


async def login(request: Request, background_tasks: BackgroundTasks, otadb: Session, username: str,
                password: str, activity: dict, fcm_token: Optional[str]) -> dict:
    try:
        user_auth = authenticate_user(username, password, user=None)
        if user_auth['status'] != 200:
            return common_response(user_auth['status'], user_auth['message'])
        user = user_auth['user']

        two_factor_response = await two_factor_policy_settings(user)
        if two_factor_response['two_factor_auth_enabled'] and user.is_2fa_enabled:
            return _two_factor_challenge(user, activity, fcm_token, two_factor_response, background_tasks, otadb)
        return await _complete_login(user, request, activity, fcm_token, background_tasks)
    except Exception as e:
        write_log(get_error_info(e), "login")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)


async def verify_two_factor_otp(request: Request, input: Verify2FAOtpRequest, background_tasks: BackgroundTasks,
                                otadb: Session) -> dict:
    try:
        if not input.info_token:
            return common_response(status.HTTP_401_UNAUTHORIZED, INVALID_INFO_TOKEN)
        try:
            activity = decode_info_token(input.info_token)
        except Exception as e:
            write_log(get_error_info(e), "verify-2fa-otp")
            return common_response(status.HTTP_401_UNAUTHORIZED, INVALID_INFO_TOKEN)

        activity['limit_notification'] = False
        username_from_token = activity.pop("username", None)

        user = _find_user(otadb, username_from_token)
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)

        valid_otp = OTPFunctions(otadb).check_otp_validity(input.otp, user.id)
        if not valid_otp:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, INVALID_OTP)
        valid_otp.status = OtpStatus.Verified
        otadb.commit()

        fcm_token = activity.pop("fcm_token", None)
        return await _complete_login(user, request, activity, fcm_token, background_tasks)
    except Exception as e:
        write_log(get_error_info(e), "verify-2fa-otp")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        otadb.close()


def get_app_version(otadb: Session) -> dict:
    try:
        appversion = otadb.query(AppVersion).order_by(AppVersion.id.desc()).first()
        return common_response(status.HTTP_200_OK, SUCCESS, appversion)
    except Exception as e:
        write_log(get_error_info(e), "app-version")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)


# ── Sessions & tokens ────────────────────────────────────────────────────────

def _clear_exceeded_sessions(db_user, device: str):
    """
    Counts this login attempt and, if it would exceed a limit, removes the affected sessions.
    Returns (message, error_response).
    """
    is_mobile = device.lower() == UserDevices.MOBILE.value.lower()
    if is_mobile:
        db_user.logged_in_mobile += 1
    else:
        db_user.logged_in_web += 1
    db_user.total_logged_in = db_user.logged_in_web + db_user.logged_in_mobile

    if db_user.total_logged_in > db_user.total_max_login:
        result = remove_tokens(username=db_user.username, device='all')
        if not result['status']:
            return None, common_response(result['code'], result['message'])
        db_user.logged_in_web = 0
        db_user.logged_in_mobile = 0
        db_user.total_logged_in = 0
        return 'All sessions removed', None

    if db_user.logged_in_web > db_user.max_login_web:
        result = remove_tokens(username=db_user.username, device=UserDevices.DESKTOP)
        if not result['status']:
            return None, common_response(result['code'], result['message'])
        db_user.logged_in_web = 0
        db_user.total_logged_in = max(db_user.logged_in_mobile, 0)
        return f'All {device} sessions removed', None

    if db_user.logged_in_mobile > db_user.max_login_mobile:
        result = remove_tokens(username=db_user.username, device=UserDevices.MOBILE)
        if not result['status']:
            return None, common_response(result['code'], result['message'])
        db_user.logged_in_mobile = 0
        db_user.total_logged_in = max(db_user.logged_in_web, 0)
        return f'All {device} session removed', None

    # No limit exceeded: undo the count
    if is_mobile:
        db_user.logged_in_mobile -= 1
    else:
        db_user.logged_in_web -= 1
    db_user.total_logged_in = db_user.logged_in_web + db_user.logged_in_mobile
    return f"Max session not exceeded for {device}. No session was removed.", None


def remove_session(otadb: Session, username: str, password: str, device: str) -> dict:
    try:
        db_user = otadb.query(UserModel).filter(UserModel.username == username).first()
        if not db_user:
            return common_response(status.HTTP_404_NOT_FOUND, "User not found")

        user_auth = authenticate_user(username, password, user=db_user)
        if user_auth['status'] != 200:
            return common_response(user_auth['status'], user_auth['message'])

        message, error = _clear_exceeded_sessions(db_user, device)
        if error:
            return error
        otadb.commit()
        return common_response(status.HTTP_200_OK, message)
    except Exception as e:
        otadb.rollback()
        write_log(get_error_info(e), "remove-session")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        if otadb:
            otadb.close()


async def refresh_access_token(otadb: Session, refresh_token: Optional[str], device: str, device_id: Optional[str]):
    try:
        if refresh_token is None:
            return common_response(status.HTTP_401_UNAUTHORIZED, INVALID_REFRESH_TOKEN)
        if refresh_token.lower().startswith("bearer "):
            refresh_token = refresh_token[7:].strip()

        payload = await token_validation(token=refresh_token, refresh_token=True)
        if payload is None:
            return common_response(status.HTTP_401_UNAUTHORIZED, INVALID_REFRESH_TOKEN)
        user = _find_user(otadb, payload['username'], oldest_first=True)
        if not user:
            return common_response(status.HTTP_401_UNAUTHORIZED, INCORRECT_USERNAME_OR_PASS)

        return await get_user_token(user, additionalInfo={"device": device, "device_id": device_id}, token_only=True)
    except Exception as e:
        write_log(get_error_info(e), "refresh-token")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, e)
    finally:
        otadb.close()


# ── Forgot password ──────────────────────────────────────────────────────────

def forgot_password(request: ForgotPasswordRequest, background_tasks: BackgroundTasks, otadb: Session) -> dict:
    try:
        user = _find_user(otadb, request.username, active_only=False, oldest_first=True)
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
        if not user.email:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, WE_COULD_NOT_FOUND_YOUR_EMAIL)

        otp_result = OTPFunctions(otadb).create_otp(user)
        if otp_result['status'] not in (201, 409):
            return common_response(otp_result['status'], otp_result['message'])

        _send_otp_email(background_tasks, user, otp_result['otp'], _PASSWORD_RESET_OTP_BODY)
        if user.phone and int(IS_SMS_ENABLED):
            send_sms({
                "phone": user.phone,
                "message": f"Please use the following otp to reset your password. This OTP is valid for the next {OTP_EXPIRES_TIME} minutes.\n OTP: {otp_result['otp']}",
            })
        return common_response(status.HTTP_200_OK, OTP_SEND_TO_EMAIL_PHONE)
    except Exception as e:
        write_log(get_error_info(e), "forgot-password")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        otadb.close()


def resend_otp(request: ForgotPasswordRequest, background_tasks: BackgroundTasks, otadb: Session) -> dict:
    try:
        user = _find_user(otadb, request.username, oldest_first=True)
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
        if not user.email:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, WE_COULD_NOT_FOUND_YOUR_EMAIL)

        otp_functions = OTPFunctions(otadb)
        if not otp_functions.can_regenerate_otp(user.id):
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, CANNOT_GENERATE_OTP)
        otp_result = otp_functions.create_otp(user)
        if otp_result['status'] not in (201, 409):
            return common_response(otp_result['status'], otp_result['message'])

        _send_otp_email(background_tasks, user, otp_result['otp'], _PASSWORD_RESET_OTP_BODY)
        if user.phone and int(IS_SMS_ENABLED):
            send_sms({
                "phone": user.phone,
                "message": f"Please use the following otp to reset your password.\n otp: {otp_result['otp']}",
            })
        return common_response(status.HTTP_200_OK, OTP_SEND_TO_EMAIL_PHONE)
    except Exception as e:
        write_log(get_error_info(e), "resend-otp")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        otadb.close()


def verify_otp(request: VerifyOtpRequest, otadb: Session) -> dict:
    try:
        user = _find_user(otadb, request.username)
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)

        valid_otp = OTPFunctions(otadb).check_otp_validity(request.otp, user.id)
        if not valid_otp:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, INVALID_OTP)

        valid_otp.status = OtpStatus.Verified
        otadb.commit()
        return common_response(status.HTTP_200_OK, OTP_VERIFIED)
    except Exception as e:
        write_log(get_error_info(e), "verify-otp")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        otadb.close()


async def reset_forgot_password(request: ResetForgetPasswordRequest, otadb: Session) -> dict:
    try:
        user = _find_user(otadb, request.username)
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
        if request.password != request.confirm_password:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, CONFIRM_PASSWORD_NOT_METCHED)
        policy_errors = await validate_password_policy(request.password)
        if policy_errors:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, policy_errors)
        if not OTPFunctions(otadb).check_verified_otp_validity(user.id):
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, SESSION_EXPIRED)

        user.password = hash_password(request.password)
        otadb.add(ChangePasswordLogs(username=user.username, password=user.password, changed_by=user.username))
        remove_tokens(username=user.username, device='all')

        user.first_login = False
        user.logged_in_web = 0
        user.logged_in_mobile = 0
        user.total_logged_in = 0

        otadb.commit()
        return common_response(status.HTTP_200_OK, PASSWORD_UPDATED)
    except Exception as e:
        write_log(get_error_info(e), "reset-forgot-password")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        otadb.close()
