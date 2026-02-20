from app.models.otadb.PasswordPolicySettings import PasswordPolicySettings
from app.models.otadb.ChangePasswordLogs import ChangePasswordLogs
from app.helpers.common import *
from datetime import datetime, timezone
import re

def validate_password_length(password, min_length):
    if len(password) < min_length:
        return f"Password must be at least {min_length} characters long"
    return None

def validate_password_strength(password, strength):
    if strength == "alphanumeric":
        if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
            return "Password must contain at least one letter and one digit"

    elif strength == "special_alphanumeric":
        if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password) and re.search(r'[^A-Za-z0-9]', password)):
            return "Password must contain both letters, numbers, and at least one special character"

    return None

async def password_policy_settings(current_user):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        policy = otadb.query(PasswordPolicySettings).first()
        response = {
            "password_reset_required": False,
            "password_reset_reason": None,
        }

        if not policy:
            return response
        
        if policy.reset_password_on_first_login and current_user.first_login:
            response["password_reset_required"] = True
            response["password_reset_reason"] = "First Login"
            return response
        
        if not policy.password_expiration_enabled:
            return response
        
        last_password_change = (
            otadb.query(ChangePasswordLogs)
            .filter(ChangePasswordLogs.username == current_user.username)
            .order_by(ChangePasswordLogs.changed_at.desc())
            .first()
        )

        if not last_password_change:
            response["password_reset_required"] = True
            response["password_reset_reason"] = "Expired"
            return response
        
        current_date = datetime.now(timezone.utc).date()
        last_change_date = last_password_change.changed_at.date()
        days_since_last_change = (current_date - last_change_date).days

        if (
            policy.password_expiration_days is not None
            and days_since_last_change >= policy.password_expiration_days
        ):
            response["password_reset_required"] = True
            response["password_reset_reason"] = "Expired"

        return response
    except Exception as e:
        write_log(get_error_info(e), "password_policy_settings")
        return {
            "password_reset_required": False,
            "password_reset_reason": None,
        }
    finally:
        if otadb is not None:
            otadb.close()

async def two_factor_policy_settings(current_user):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        policy = otadb.query(PasswordPolicySettings).first()
        response = {
            "two_factor_auth_enabled": False,
            "otp_sending_option": None
        }

        if not policy:
            return response
        
        if (
            policy.two_factor_auth_enabled
            and policy.two_factor_roles
            and current_user.users_roles
        ):
            if current_user.users_roles.lower() in policy.two_factor_roles:
                response["two_factor_auth_enabled"] = True
                response["otp_sending_option"] = policy.otp_sending_option
        return response
    except Exception as e:
        write_log(get_error_info(e), "two_factor_policy_settings")
        return {
            "two_factor_auth_enabled": False,
            "otp_sending_option": None,
        }
    finally:
        if otadb is not None:
            otadb.close()
   
async def validate_password_policy(password: str):
    otadb = None
    try:
        otadb = next(get_ota_db_session())
        error_messages = []
        policy = otadb.query(PasswordPolicySettings).first()

        if policy:
            if policy.password_strength:
                msg = validate_password_strength(password, policy.password_strength)
                if msg:
                    error_messages.append(msg)

            if policy.min_password_length is not None:
                msg = validate_password_length(password, policy.min_password_length)
                if msg:
                    error_messages.append(msg)

        return ". ".join(error_messages)
    except Exception as e:
        write_log(get_error_info(e), "validate_password_policy")
        return "Internal server error"
    finally:
        if otadb is not None:
            otadb.close()

def validate_2fa_contact_info(
    otp_sending_option: str,
    user,
    is_email_enabled: bool,
    is_sms_enabled: bool,
):
    missing = []
    channel_checks = {
        "email": (
            is_email_enabled,
            user.email,
            "email",
            "a valid email"
        ),
        "mobile": (
            is_sms_enabled,
            user.phone,
            "mobile number",
            "a valid mobile number"
        ),
    }
    required_channels = []
    
    if otp_sending_option == "both":
        required_channels = ["email", "mobile"]
    elif otp_sending_option in channel_checks:
        required_channels = [otp_sending_option]

    for channel in required_channels:
        is_enabled, value, _, message = channel_checks[channel]
        if is_enabled and not value:
            missing.append(message)

    if missing:
        msg = (
            "Two factor authentication is enabled. "
            "You need to have " + " and ".join(missing) + "."
        )
        return True, msg

    return False, None

