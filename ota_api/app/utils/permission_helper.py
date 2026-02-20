from . import *
import json
import os
from fastapi import Request, status as http_status
from app.helpers.common import write_log, get_error_info, common_response
from app.helpers.constants import INTERNAL_SERVER_ERROR

ALL_PERMISSIONS_FILE = os.path.join(os.path.dirname(__file__), "../permissions/all_permissions.json")
ROLE_PERMISSIONS_FILE = os.path.join(os.path.dirname(__file__), "../permissions/role_permissions.json")

def load_permissions(source: str) -> dict:
    file_map = {
        "all": ALL_PERMISSIONS_FILE,
        "role": ROLE_PERMISSIONS_FILE
    }
    file_path = file_map.get(source)
    if not file_path:
        write_log("PermissionFileError", f"Invalid permission source: {source}")
        return {}
    try:
        if not os.path.exists(file_path):
            if source == "role":
                initial_content = {
                    "admin": [
                        "view_admin_users",
                        "view_broker_users",
                        "view_psp_users",
                        "create_admin_user",
                        "create_broker_user",
                        "create_psp_user",
                        "update_admin_user",
                        "update_broker_user",
                        "update_psp_user",
                        "delete_admin_user",
                        "delete_broker_user",
                        "delete_psp_user",
                        "view_broker_list",
                        "view_broker_psp_config",
                        "history_broker_psp_config",
                        "create_broker_profile",
                        "create_broker_psp_config",
                        "update_broker_profile",
                        "update_broker_psp_config",
                        "delete_broker_profile",
                        "view_psp_list",
                        "create_psp_profile",
                        "update_psp_profile",
                        "delete_psp_profile",
                        "view_ip_whitelist",
                        "create_ip_whitelist",
                        "update_ip_whitelist",
                        "delete_ip_whitelist",
                        "view_dashboard_analytics",
                        "view_api_logs",
                        "view_callback_api_logs",
                        "view_idm",
                        "update_permissions"
                    ],
                    "broker": [],
                    "psp": []
                }
            elif source == "all":
                initial_content = {
                    "user": [
                        "view_admin_users",
                        "view_broker_users",
                        "view_psp_users",
                        "create_admin_user",
                        "create_broker_user",
                        "create_psp_user",
                        "update_admin_user",
                        "update_broker_user",
                        "update_psp_user",
                        "delete_admin_user",
                        "delete_broker_user",
                        "delete_psp_user"
                    ],
                    "broker": [
                        "view_broker_list",
                        "view_broker_psp_config",
                        "history_broker_psp_config",
                        "create_broker_profile",
                        "create_broker_psp_config",
                        "update_broker_profile",
                        "update_broker_psp_config",
                        "delete_broker_profile"
                    ],
                    "psp": [
                        "view_psp_list",
                        "create_psp_profile",
                        "update_psp_profile",
                        "delete_psp_profile"
                    ],
                    "ip_whitelist": [
                        "view_ip_whitelist",
                        "create_ip_whitelist",
                        "update_ip_whitelist",
                        "delete_ip_whitelist"
                    ],
                    "dashboard": [
                        "view_dashboard_analytics"
                    ],
                    "logs": [
                        "view_api_logs",
                        "view_callback_api_logs"
                    ],
                    "idm": [
                        "view_idm"
                    ],
                    "permissions": [
                        "update_permissions"
                    ]
                }
            else:
                initial_content = {}

            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(initial_content, f)
            return initial_content
        
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        write_log("PermissionFileError", f"Permission file not found: {file_path}")
        return {}
    except json.JSONDecodeError as e:
        write_log("PermissionFileError", f"Invalid JSON format in permission file: {str(e)}")
        return {}
    except Exception as ex:
        write_log("PermissionFileError", get_error_info(ex))
        return {}

def has_permission(role: str, permission: str) -> bool:
    try:
        role_permissions = load_permissions('role')
        allowed_permissions = role_permissions.get(role.lower(), [])
        return permission in allowed_permissions
    except Exception as ex:
        write_log("Error@has_permission", get_error_info(ex))
        return False

async def require_permission(request: Request, permission: str):
    """
    Checks if the currently logged-in user has the given permission.
    Returns a common_response if unauthorized, None if allowed.
    """
    try:
        current_user = getattr(request.state, "user", None)
        if not current_user:
            return common_response(
                http_status.HTTP_401_UNAUTHORIZED,
                "Unauthenticated user.",
                {}
            )

        role = getattr(current_user, "user_role", None)
        if not role:
            return common_response(
                http_status.HTTP_403_FORBIDDEN,
                "User role not found.",
                {}
            )

        if not has_permission(role, permission):
            return common_response(
                http_status.HTTP_403_FORBIDDEN,
                f"'{role.lower()}' role does not have permission '{permission}'",
                {}
            )

        return None

    except Exception as ex:
        write_log("Error@require_permission", get_error_info(ex))
        return common_response(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            INTERNAL_SERVER_ERROR,
            {},
            str(ex)
        )
