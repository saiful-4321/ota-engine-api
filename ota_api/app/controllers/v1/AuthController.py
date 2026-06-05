# app.controllers.authController.py
from . import *
from typing import Optional
from sqlalchemy.orm import Session
from app.helpers.authentication import *
from app.helpers.password_policy import *
from app.services.otp import OTPFunctions
from app.services.mail import MailFunctions
from app.models.otadb.User import User as UserModel
from app.models.otadb.Otp import OtpStatus
from app.helpers.password_utils import verify_password, hash_password
from fastapi import APIRouter, Depends, status, BackgroundTasks, Header, Request, Form
from fastapi.security import OAuth2PasswordRequestForm, OAuth2AuthorizationCodeBearer
from app.models.otadb.AppVersion import AppVersion
from app.helpers.authentication import create_access_token, register_fcm_token, token_validation
from app.models.schemas import Verify2FAOtpRequest, ForgotPasswordRequest, VerifyOtpRequest, ResetForgetPasswordRequest
# from app.models.otadb.ClientsActive import ClientsActive
from app.models.otadb.User import User
from app.models.otadb.UserSetting import UserSetting
from app.models.enums import UserDevices
from types import SimpleNamespace
from app.utils.sms_utils import send_sms
from config import SECRET_2FA, IS_SMS_ENABLED, IS_EMAIL_ENABLED, IS_SELF_SIGNUP_ENABLED, IS_CRED_EMAIL_ENABLED, IS_CRED_SMS_ENABLED, OTP_EXPIRES_TIME
import uuid
import base64
from app.models.enums import UserDevices

router = APIRouter()

@router.post("/app-version")
async def loging(otadb: Session = Depends(get_ota_db_session)):
    try:
        appversion = otadb.query(AppVersion).order_by(AppVersion.id.desc()).first()

        return common_response(status.HTTP_200_OK, SUCCESS, appversion)
    except Exception as e:
        write_log(get_error_info(e), "app-version")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
 
@router.post("/login")
async def login(
    request: Request, 
    background_tasks: BackgroundTasks,
    login_data: OAuth2PasswordRequestForm = Depends(), 
    device: str = Form(UserDevices.MOBILE.value, max_length=150),
    device_id: str = Form(None, max_length=150),
    os: str = Form(None, max_length=30),
    browser: str = Form(None, max_length=100),
    location: str = Form(None, max_length=300),
    fcm_token: str = Form(None, max_length=300),
    otadb: Session = Depends(get_ota_db_session)
):
    try:
        activity = {
            "device": device,
            "os": os,
            "browser": browser,
            "location": location,
            "ip": request.client.host,
            "device_id": device_id,
            "limit_notification": True,
        }
        user_auth = authenticate_user(login_data.username, login_data.password, user=None)
        if user_auth['status'] != 200:
            return common_response(user_auth['status'], user_auth['message'])

        user = user_auth['user']
        
        two_factor_response = await two_factor_policy_settings(user)
        if two_factor_response['two_factor_auth_enabled'] and user.is_2fa_enabled:
            two_factor_response.pop('two_factor_auth_enabled')
            otp_sending_option = two_factor_response.pop('otp_sending_option')
            activity['username'] = user.username
            activity['fcm_token'] = fcm_token
            json_bytes = json.dumps(activity, separators=(',', ':'), sort_keys=True).encode('utf-8')
            key_bytes = SECRET_2FA.encode('utf-8')
            encrypted_bytes = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(json_bytes)])
            encrypted_info = base64.b64encode(encrypted_bytes).decode('utf-8')
            two_factor_response['info_token'] = encrypted_info
            
            if not IS_EMAIL_ENABLED and not IS_SMS_ENABLED:
                return common_response(status.HTTP_400_BAD_REQUEST, NO_EMAIL_SMS_SERVICE, two_factor_response)
            if otp_sending_option == 'email' and not IS_EMAIL_ENABLED:
                    if user.email:
                        return common_response(status.HTTP_400_BAD_REQUEST, TWO_FA_EMAIL_SERVICE_NOT_ENABLED, two_factor_response)
                    else: 
                        return common_response(status.HTTP_400_BAD_REQUEST, TWO_FA_EMAIL_SERVICE_NOT_ENABLED_FOUND, two_factor_response)
            elif otp_sending_option == 'mobile' and not IS_SMS_ENABLED:
                    if user.phone:
                        return common_response(status.HTTP_400_BAD_REQUEST, TWO_FA_SMS_SERVICE_NOT_ENABLED, two_factor_response)
                    else:
                        return common_response(status.HTTP_400_BAD_REQUEST, TWO_FA_SMS_SERVICE_NOT_ENABLED_FOUND, two_factor_response)
            else:
                has_error, message = validate_2fa_contact_info(
                    otp_sending_option,
                    user,
                    IS_EMAIL_ENABLED,
                    IS_SMS_ENABLED
                )
                if has_error:
                    return common_response(status.HTTP_400_BAD_REQUEST, message, two_factor_response)
            
            otp_functions = OTPFunctions(otadb)
            otp_result = otp_functions.create_otp(user)
            if otp_result['status'] not in (201, 409):
                return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, otp_result['message'], two_factor_response)
            
            sent_channels = []
            if otp_sending_option in ('both', 'email') and IS_EMAIL_ENABLED and user.email:
                email_parts = user.email.split('@')
                sent_channels.append(f"{email_parts[0][:2]}*******@{email_parts[1]}")
                subject = "One-Time Password (OTP)"
                body = f"""
                        Please use the following OTP to proceed with two factor authentication.<br><br>
                        This OTP is valid for the next <b>{OTP_EXPIRES_TIME}</b> minutes.<br><br>"""
                button = {
                    "text": "OTP: " + str(otp_result['otp']),
                    "link": "#"
                }
                mail_functions = MailFunctions(recipient_email=user.email, subject=subject, body=body, userInfo=user, button=button)
                background_tasks.add_task(mail_functions.send_email)
            if otp_sending_option in ('both', 'mobile') and IS_SMS_ENABLED and user.phone:
                sent_channels.append(f"{user.phone[:4]}*******{user.phone[-4:]}")
                sms_body = f"Please use the following otp for two factor authentication.\n OTP: {otp_result['otp']}"
                send_sms({
                "phone": user.phone,
                "message": sms_body,
                })
            if sent_channels:
                OTP_response_message = (
                    "An OTP was sent to your "
                    + " and ".join(sent_channels)
                    + "."
                )
            else:
                OTP_response_message = (
                    "Two factor authentication is enabled, "
                    "but no valid delivery channel is available."
                )
                return common_response(status.HTTP_400_BAD_REQUEST, OTP_response_message, two_factor_response)
            return common_response(status.HTTP_206_PARTIAL_CONTENT, OTP_response_message, two_factor_response)
        else:        
            if fcm_token:
                background_tasks.add_task(register_fcm_token, username=user.username, fcm_token=fcm_token)
            login_limit = handle_login_limit(user=user, request=request, activity=activity)
            if login_limit['status'] == True:
                response =  await get_user_token(user=user, additionalInfo=activity)
                password_policy_response = await password_policy_settings(user)
                response.update(password_policy_response)
                return common_response(status.HTTP_200_OK, SUCCESS, response)
            else:
                return common_response(login_limit['code'], login_limit['message'])
    except Exception as e:
        write_log(get_error_info(e), "login")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    

@router.post("/remove-session")
async def remove_session(
    request: Request,
    login_data: OAuth2PasswordRequestForm = Depends(),
    device: str = Form("Mobile", max_length=150),
    otadb: Session = Depends(get_ota_db_session)
):
    try:
        db_user = otadb.query(UserModel).filter(UserModel.username == login_data.username).first()
        if not db_user:
            return common_response(status.HTTP_404_NOT_FOUND, "User not found")
        
        message = f"Max session not exceeded for {device}. No session was removed."
        user_auth = authenticate_user(login_data.username, login_data.password, user=db_user)
        if user_auth['status'] != 200:
            return common_response(user_auth['status'], user_auth['message'])

        if device.lower() == UserDevices.MOBILE.value.lower():
            db_user.logged_in_mobile += 1
        else:
            db_user.logged_in_web += 1
        db_user.total_logged_in = db_user.logged_in_web + db_user.logged_in_mobile

        if db_user.total_logged_in > db_user.total_max_login:            
            result = remove_tokens(
                username=db_user.username,
                device='all'
            )
            if not result['status']:
                return common_response(result['code'], result['message'])
            db_user.logged_in_web = 0
            db_user.logged_in_mobile = 0
            db_user.total_logged_in = 0 
            message = 'All sessions removed'

        elif db_user.logged_in_web > db_user.max_login_web:            
            result = remove_tokens(
                username=db_user.username,
                device=UserDevices.DESKTOP
            )

            if not result['status']:
                return common_response(result['code'], result['message'])   
            
            db_user.logged_in_web = 0
            db_user.total_logged_in = max(db_user.logged_in_mobile, 0)
            message = f'All {device} sessions removed'

        elif db_user.logged_in_mobile > db_user.max_login_mobile:
            result = remove_tokens(
                username=db_user.username,
                device=UserDevices.MOBILE
            )

            if not result['status']:
                return common_response(result['code'], result['message'])

            db_user.logged_in_mobile = 0
            db_user.total_logged_in = max(db_user.logged_in_web, 0)   
            message = f'All {device} session removed' 

        else:
            if device.lower() == UserDevices.MOBILE.value.lower():
                db_user.logged_in_mobile -= 1
            else:
                db_user.logged_in_web -= 1
            db_user.total_logged_in = db_user.logged_in_web + db_user.logged_in_mobile
        otadb.commit()
        return common_response(status.HTTP_200_OK, message)
    except Exception as e:
        otadb.rollback()
        write_log(get_error_info(e), "remove-session")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        if otadb:
            otadb.close()

@router.post("/refresh-token")
async def refresh_access_token(
    refresh_token: str = Header(None, alias="refresh-token"), 
    device: str = Form("Mobile", max_length=150), 
    device_id: str = Form(None, max_length=150),
    otadb: Session = Depends(get_ota_db_session)
):
    try:
        if refresh_token is None:
            return common_response(status.HTTP_401_UNAUTHORIZED, INVALID_REFRESH_TOKEN)

        if refresh_token.lower().startswith("bearer "):
            refresh_token = refresh_token[7:].strip()

        payload = await token_validation(token=refresh_token, refresh_token=True)
        if payload is None:
            return common_response(status.HTTP_401_UNAUTHORIZED, INVALID_REFRESH_TOKEN)
        user = otadb.query(UserModel).filter(func.lower(UserModel.username) == payload['username'].lower()).filter(UserModel.account_status == "active").order_by(UserModel.id.asc()).first()
        if not user:
            return common_response(status.HTTP_401_UNAUTHORIZED, INCORRECT_USERNAME_OR_PASS)

        return await get_user_token(user, additionalInfo={"device": device, "device_id": device_id}, token_only=True)
    except Exception as e:
        write_log(get_error_info(e), "refresh-token")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, e)
    finally:
        otadb.close()

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, background_tasks: BackgroundTasks, otadb: Session = Depends(get_ota_db_session)):
    try:
        user = otadb.query(UserModel).filter(func.lower(UserModel.username) == request.username.lower()).order_by(UserModel.id.asc()).first()
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
        if not user.email:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, WE_COULD_NOT_FOUND_YOUR_EMAIL)

        # creating an instance of OTPFunctions
        otp_functions = OTPFunctions(otadb)
        
        # creating otp
        otp_result = otp_functions.create_otp(user)

        if otp_result['status'] not in (201, 409):
            return common_response(otp_result['status'], otp_result['message'])
        
        recipient_email = user.email
        subject = "One-Time Password (OTP)"
        body = f"""
            Please use the following OTP to proceed with resetting your password.<br><br>
            This OTP is valid for the next <b>{OTP_EXPIRES_TIME}</b> minutes.<br><br>
            If you did not request a password reset, please ignore this message or contact our support team.
        """

        button = {
            "text": "OTP: " + str(otp_result['otp']),
            "link": "#"
        }
        # Call the common function to send the email
        mail_functions = MailFunctions(recipient_email=recipient_email, subject=subject, body=body, userInfo=user, button=button)
        # Sending the email as background task

        background_tasks.add_task(mail_functions.send_email)

        if user.phone and int(IS_SMS_ENABLED):
            sms_body = f"Please use the following otp to reset your password. This OTP is valid for the next {OTP_EXPIRES_TIME} minutes.\n OTP: {otp_result['otp']}"
            send_sms({
                "phone": user.phone,
                "message": sms_body,
            })

        return common_response(status.HTTP_200_OK, OTP_SEND_TO_EMAIL_PHONE)
    except Exception as e:
        write_log(get_error_info(e), "forgot-password")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        otadb.close()
  
@router.post("/resend-otp")
async def resend_otp(request: ForgotPasswordRequest, background_tasks: BackgroundTasks, otadb: Session = Depends(get_ota_db_session)):
    try:
        user = otadb.query(UserModel).filter(func.lower(UserModel.username) == request.username.lower()).filter(UserModel.account_status == "active").order_by(UserModel.id.asc()).first()
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
        if not user.email:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, WE_COULD_NOT_FOUND_YOUR_EMAIL)

        otp_functions = OTPFunctions(otadb)

        if not otp_functions.can_regenerate_otp(user.id):
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, CANNOT_GENERATE_OTP)
    
        otp_result = otp_functions.create_otp(user)

        # Check the result and handle accordingly
        if otp_result['status'] not in (201, 409):
            return common_response(otp_result['status'], otp_result['message'])
        
        # @to-do, need to sent otp mail
        recipient_email = user.email
        subject = "One-Time Password (OTP)"
        body = f"""
            Please use the following OTP to proceed with resetting your password.<br><br>
            This OTP is valid for the next <b>{OTP_EXPIRES_TIME}</b> minutes.<br><br>
            If you did not request a password reset, please ignore this message or contact our support team.
        """
        button = {
            "text": "OTP: " + str(otp_result['otp']),
            "link": "#"
        }
        mail_functions = MailFunctions(recipient_email=recipient_email, subject=subject, body=body, userInfo=user, button=button)
        background_tasks.add_task(mail_functions.send_email)

        if user.phone and int(IS_SMS_ENABLED):
            sms_body = f"Please use the following otp to reset your password.\n otp: {otp_result['otp']}"
            send_sms({
                "phone": user.phone,
                "message": sms_body,
            })

        return common_response(status.HTTP_200_OK, OTP_SEND_TO_EMAIL_PHONE)
    except Exception as e:
        write_log(get_error_info(e), "resend-otp")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        otadb.close()
        
@router.post("/verify-otp")
async def verify_otp(request: VerifyOtpRequest, otadb: Session = Depends(get_ota_db_session)):
    try:
        user = otadb.query(UserModel).filter(func.lower(UserModel.username) == request.username.lower()).filter(UserModel.account_status == "active").first()   
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
        otp_functions = OTPFunctions(otadb)
        valid_otp = otp_functions.check_otp_validity(request.otp, user.id)

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

@router.post("/reset-forgot-password")
async def reset_forgot_password(
    request: ResetForgetPasswordRequest, 
    otadb: Session = Depends(get_ota_db_session), 
):
    try:
        user = otadb.query(UserModel).filter(func.lower(UserModel.username) == request.username.lower()).filter(UserModel.account_status == "active").first()   
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
        if request.password != request.confirm_password:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, CONFIRM_PASSWORD_NOT_METCHED)
        policy_errors = await validate_password_policy(request.password)
        if policy_errors:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, policy_errors)  
        
        otp_functions = OTPFunctions(otadb)        
        if not otp_functions.check_verified_otp_validity(user.id):
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, SESSION_EXPIRED)

        user.password = hash_password(request.password)

        change_password_log = ChangePasswordLogs(username=user.username, password=user.password, changed_by=user.username)
        otadb.add(change_password_log)
        
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
    


# @router.post('/signup')
# async def client_self_signup(background_tasks: BackgroundTasks, input: SignupSchema, otadb: Session = Depends(get_ota_db_session)):
#     try:
#         if not input.is_tc_accepted:
#             return common_response(status.HTTP_400_BAD_REQUEST, T_C_NOT_ACCEPTED)
        
#         if not int(IS_SELF_SIGNUP_ENABLED):
#             return common_response(status.HTTP_400_BAD_REQUEST, SELF_SIGNUP_DISABLED)
        
#         client_exists = otadb.query(ClientsActive).filter(ClientsActive.ClientCode == input.client_code).first()
#         if not client_exists: 
#             return common_response(status.HTTP_404_NOT_FOUND, INVALID_CLIENT_CODE)
        
#         user_exist = otadb.query(User).filter(func.lower(User.username) == input.client_code.lower()).first()
#         if user_exist:
#             return common_response(status.HTTP_409_CONFLICT, USER_ALREADY_EXISTS)
        
#         if not client_exists.email and not client_exists.phone:
#             return common_response(status.HTTP_404_NOT_FOUND, EMAIL_PHONE_MISSING)
        
#         user = SimpleNamespace(
#             id=None,
#             name=client_exists.Name,
#             username=input.client_code,
#             email=None,
#             phone=None,
#         )

#         message = ""
#         if client_exists.email and int(IS_EMAIL_ENABLED):
#             user.email = client_exists.email
#             email_parts = client_exists.email.split('@')
#             message += f"OTP sent to your email: {email_parts[0][:2]}*******@{email_parts[1]}."

#         if client_exists.phone and int(IS_SMS_ENABLED):
#             user.phone =client_exists.phone
#             message += f"OTP sent to your phone: {client_exists.phone[:4]}*******{client_exists.phone[-4:]}."

#         if client_exists.email and client_exists.phone and int(IS_EMAIL_ENABLED) and int(IS_SMS_ENABLED):
#             email_parts = client_exists.email.split('@')
#             message = f"OTP sent to your email: {email_parts[0][:2]}*******@{email_parts[1]} and phone: {client_exists.phone[:4]}*******{client_exists.phone[-4:]}."

#         otp_functions = OTPFunctions(otadb)
#         otp_result = otp_functions.create_otp(user)

#         if otp_result['status'] not in (201, 409):
#             return common_response(otp_result['status'], otp_result['message'])
        
#         if client_exists.email and int(IS_EMAIL_ENABLED):
#             subject = "One-Time Password (OTP)"
#             body = f"""
#                 Please use the following OTP to proceed with register your account.<br><br>
#                 This OTP is valid for the next <b>{OTP_EXPIRES_TIME}</b> minutes.<br><br>
#                 If you did not request a password reset, please ignore this message or contact our support team.
#             """

#             button = {
#                 "text": "OTP: " + str(otp_result['otp']),
#                 "link": "#"
#             }

#             # Call the common function to send the email
#             mail_functions = MailFunctions(recipient_email=client_exists.email, subject=subject, body=body, userInfo=user, button=button)
#             background_tasks.add_task(mail_functions.send_email)
        
#         if client_exists.phone and int(IS_SMS_ENABLED):
#             send_sms({
#                 "phone": client_exists.phone,
#                 "message": f"Please use the following otp to register your account.\n otp: {otp_result['otp']}",
#             })
#         return common_response(status.HTTP_200_OK, SUCCESS, { "message": message })
#     except Exception as e:
#         write_log(get_error_info(e), '/signup')
#         return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
#     finally:
#         otadb.close()

# @router.post('/signup-confirm')
# async def client_self_signup(background_tasks: BackgroundTasks, input: SignupConfirmSchema, otadb: Session = Depends(get_ota_db_session)):
#     try:
#         if not int(IS_SELF_SIGNUP_ENABLED):
#             return common_response(status.HTTP_400_BAD_REQUEST, SELF_SIGNUP_DISABLED)
        
#         client_exists = otadb.query(ClientsActive).filter(ClientsActive.ClientCode == input.client_code).first()
#         if not client_exists: 
#             return common_response(status.HTTP_404_NOT_FOUND, INVALID_CLIENT_CODE)
        
#         user_exist = otadb.query(User).filter(func.lower(User.username) == input.client_code.lower()).first()
#         if user_exist:
#             return common_response(status.HTTP_409_CONFLICT, USER_ALREADY_EXISTS)
        
#         otp_functions = OTPFunctions(otadb)
#         valid_otp = otp_functions.check_otp_validity_by_username(input.otp, input.client_code)
#         if not valid_otp:
#             return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, INVALID_OTP)
        
#         valid_otp.status = OtpStatus.Verified
#         new_user_id = 'C_' + str(uuid.uuid4())

#         user_settings = UserSetting(user_id=new_user_id, username=input.client_code, otp=input.otp, sms_status=False, email_status=True)
#         otadb.add(user_settings)

#         password = await generate_random_password()
#         user = User(
#             name=client_exists.Name,
#             email=client_exists.email,
#             phone=client_exists.phone,
#             username=input.client_code,
#             user_id=new_user_id,
#             acc_type='client',
#             users_roles='client',
#             branch='HEAD OFFICE',
#             email_status='Verified',
#             phone_status='Verified',
#             account_status='active',
#             parking_enabled=False,
#             password=generate_password_hash(password=password),
#             max_login_web=1,
#             max_login_mobile=1,
#             logged_in=0,
#             logged_in_mobile=0,
#             total_max_login=1,
#             total_logged_in=0,
#             first_login=True,
#             is_2fa_enabled=True
#         )
#         otadb.add(user)
#         otadb.commit()
#         otadb.refresh(user)

#         if client_exists.email and int(IS_EMAIL_ENABLED) and int(IS_CRED_EMAIL_ENABLED):
#             subject = "Important: Your Login Credentials"
#             body = """
#                 Please use the following Credentials to proceed with login your account.<br><br>
#                 Please change your password once you logged in.<br><br>
#                 If this email is not related to you, please ignore this message or contact our support team.
#             """
#             button = {
#                 "text": f"username: {input.client_code} \n password: {password}",
#                 "link": "#"
#             }
#             mail_functions = MailFunctions(recipient_email=client_exists.email, subject=subject, body=body, userInfo=user, button=button)
#             background_tasks.add_task(mail_functions.send_email)
#         if client_exists.phone and int(IS_SMS_ENABLED) and int(IS_CRED_SMS_ENABLED):
#             send_sms({
#                 "phone": client_exists.phone,
#                 "message": f"Please use the following credentials to login your account.\n username: {input.client_code} \n password: {password}",
#             })

#         message = ""
#         if client_exists.email and int(IS_EMAIL_ENABLED) and int(IS_CRED_EMAIL_ENABLED): 
#             user.email = client_exists.email
#             email_parts = client_exists.email.split('@')
#             message += f"Credentials sent to your email: {email_parts[0][:2]}*******@{email_parts[1]}."

#         if client_exists.phone and int(IS_SMS_ENABLED) and int(IS_CRED_SMS_ENABLED):
#             user.phone =client_exists.phone
#             message += f"Credentials sent to your phone: {client_exists.phone[:4]}*******{client_exists.phone[-4:]}."

#         if client_exists.email and client_exists.phone and int(IS_EMAIL_ENABLED) and int(IS_SMS_ENABLED) and int(IS_CRED_EMAIL_ENABLED) and int(IS_CRED_SMS_ENABLED):
#             email_parts = client_exists.email.split('@')
#             message = f"Credentials sent to your email: {email_parts[0][:2]}*******@{email_parts[1]} and phone: {client_exists.phone[:4]}*******{client_exists.phone[-4:]}."

#         return common_response(status.HTTP_200_OK, message)
#     except Exception as e:
#         otadb.rollback()
#         write_log(get_error_info(e), '/signup-confirm')
#         return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
#     finally:
#         otadb.close()
    
@router.post("/verify-2fa-otp")
async def verify_otp(
    request: Request,
    input: Verify2FAOtpRequest, 
    background_tasks: BackgroundTasks, 
    otadb: Session = Depends(get_ota_db_session)
):
    try:
        if not input.info_token:
            return common_response(status.HTTP_401_UNAUTHORIZED, "Invalid information token.")
        
        try:
            encrypted_bytes = base64.b64decode(input.info_token.encode("utf-8"))
            key_bytes = SECRET_2FA.encode("utf-8")
            decrypted_bytes = bytes(
                b ^ key_bytes[i % len(key_bytes)]
                for i, b in enumerate(encrypted_bytes)
            )
            activity = json.loads(decrypted_bytes.decode("utf-8"))
        except Exception as e:
            write_log(get_error_info(e), "verify-2fa-otp")
            return common_response(status.HTTP_401_UNAUTHORIZED, "Invalid information token.")

        activity['limit_notification'] = False
        username_from_token = activity.pop("username", None)
        
        user = otadb.query(UserModel).filter(func.lower(UserModel.username) == username_from_token.lower()).filter(UserModel.account_status == "active").first()   
        if not user:
            return common_response(status.HTTP_404_NOT_FOUND, USER_NOT_FOUND)
        
        otp_functions = OTPFunctions(otadb)
        valid_otp = otp_functions.check_otp_validity(input.otp, user.id)
        if not valid_otp:
            return common_response(status.HTTP_422_UNPROCESSABLE_ENTITY, INVALID_OTP)
        valid_otp.status = OtpStatus.Verified
        otadb.commit()
        
        fcm_token = activity.pop("fcm_token", None)
        if fcm_token:
                background_tasks.add_task(register_fcm_token, username=user.username, fcm_token=fcm_token)
        login_limit = handle_login_limit(user=user, request=request, activity=activity)
        if login_limit['status'] == True:
            response =  await get_user_token(user=user, additionalInfo=activity)
            password_policy_response = await password_policy_settings(user)
            response.update(password_policy_response)
            return common_response(status.HTTP_200_OK, SUCCESS, response)
        else:
            return common_response(login_limit['code'], login_limit['message'])
    except Exception as e:
        write_log(get_error_info(e), "verify-2fa-otp")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR)
    finally:
        otadb.close()

    