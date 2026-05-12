from jose import JWTError, jwt
from sqlalchemy import func
from app.helpers.common import *
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
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
            UserRoleEnum.BROKERADMIN.value,
            UserRoleEnum.ADMINISTRATOR.value
        }

        if user.users_roles not in allowed_roles:
            return {
                "status": 403,
                "message": f"Access denied: '{user.users_roles}' type user is not allowed."
            }

        if not check_password_hash(user.password, password):
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
            user.logged_in = (user.logged_in or 0) + 1
        user.total_logged_in = user.logged_in + user.logged_in_mobile

        if (user.total_max_login or 0) <= 0:
            return {'status': False, 'code': 403, 'message': YOU_ARE_NOT_ALLOWED_TO_LOGIN_ANY_DEVICE}
        if activity['device'].lower() == UserDevices.MOBILE.value.lower() and (user.max_login_mobile or 0) <= 0:
            return {'status': False, 'code': 403, 'message': YOU_ARE_NOT_ALLOWED_TO_LOGIN_ANY_MOBILE_DEVICE}
        if activity['device'].lower() == UserDevices.DESKTOP.value.lower() and (user.max_login or 0) <= 0:
            return {'status': False, 'code': 403, 'message': YOU_ARE_NOT_ALLOWED_TO_LOGIN_ANY_DESKTOP_DEVICE}

        exceeded_web = user.logged_in > user.max_login
        exceeded_mobile = user.logged_in_mobile > user.max_login_mobile
        exceeded_total = user.total_logged_in > user.total_max_login

        if exceeded_web or exceeded_mobile or exceeded_total: 
            limit_notification = activity.get('limit_notification') if activity else None
            if limit_notification:
                login_activity(
                    user,
                    remarks=MAX_ALLOWED_LOGIN_EXTENDED_FOR_MOBILE if activity['device'].lower() == UserDevices.MOBILE.value.lower() else MAX_ALLOWED_LOGIN_EXTENDED,
                    activity=activity,
                    conn_number=user.logged_in_mobile if activity['device'].lower() == UserDevices.MOBILE.value.lower() else user.logged_in
                )
                if device_type == UserDevices.MOBILE.value.lower():
                    user.logged_in_mobile = (user.logged_in_mobile or 0) - 1
                else:
                    user.logged_in = (user.logged_in or 0) - 1
                user.total_logged_in = user.logged_in + user.logged_in_mobile
                otadb.commit()
                return {'status': False, 'code': 409, 'message': ACTIVE_SESSION_EXISTS}
            else:
                login_activity(
                    user,
                    remarks=MAX_ALLOWED_LOGIN_EXTENDED_FOR_MOBILE if activity['device'].lower() == UserDevices.MOBILE.value.lower() else MAX_ALLOWED_LOGIN_EXTENDED,
                    activity=activity,
                    conn_number=user.logged_in_mobile if activity['device'].lower() == UserDevices.MOBILE.value.lower() else user.logged_in
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
                        user.logged_in = 0
                    else:
                        user.logged_in_mobile = 0
                        user.logged_in = (user.logged_in or 0) - 1
                    user.total_logged_in = 1 
                elif exceeded_mobile:
                    result = remove_tokens(
                        username=user.username,
                        device=UserDevices.MOBILE
                    )
                    if not result['status']:
                        return {'status': False, 'code': result['code'], 'message': result['message']}
                    
                    user.logged_in_mobile = (user.logged_in_mobile or 0) - 1 
                    user.total_logged_in = user.logged_in_mobile + user.logged_in
                    
                elif exceeded_web:
                    result = remove_tokens(
                        username=user.username,
                        device=UserDevices.DESKTOP,
                    )
                    if not result['status']:
                        return {'status': False, 'code': result['code'], 'message': result['message']}
                    
                    user.logged_in = (user.logged_in or 0) - 1
                    user.total_logged_in = user.logged_in_mobile + user.logged_in

        otadb.commit()
        login_activity(
            user,
            remarks="Login",
            activity=activity,
            conn_number=user.logged_in_mobile if activity['device'].lower() == 'mobile' else user.logged_in
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