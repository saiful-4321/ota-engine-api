"""
app/helpers/permissions.py

Workflows behind the /permission endpoints: read and replace a role's permission list
(stored in the role-permissions JSON file managed by app.utils.permission_helper).
"""

import json

from fastapi import Request, status as http_status
from sqlalchemy.orm import Session

from app.helpers.common import common_response, get_error_info, write_log
from app.helpers.constants import DATA_NOT_FOUND, INTERNAL_SERVER_ERROR
from app.models.schemas import RolePermissionUpdate
from app.utils.permission_helper import ROLE_PERMISSIONS_FILE, load_permissions, require_permission

MANAGE_PERMISSION = "update_permissions"
_ADMIN_ROLES = ["admin", "superadmin"]


def _server_error(ota_db: Session, ex: Exception, source: str) -> dict:
    ota_db.rollback()
    write_log(source, get_error_info(ex))
    return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, str(ex))


def _save_role_permissions(data: dict) -> None:
    with open(ROLE_PERMISSIONS_FILE, "w") as f:
        json.dump(data, f, indent=4)


async def get_role_permissions(request: Request, role: str, ota_db: Session) -> dict:
    try:
        permission_check = await require_permission(request, MANAGE_PERMISSION)
        if permission_check:
            return permission_check

        all_permissions_data = load_permissions('all')
        if not all_permissions_data:
            return common_response(http_status.HTTP_404_NOT_FOUND, DATA_NOT_FOUND, {},
                                   "No permissions found in all_permissions.json")

        response = {
            "all_permissions": all_permissions_data,
            "active_permissions": load_permissions('role').get(role.lower(), []),
        }
        return common_response(http_status.HTTP_200_OK, f"Permissions fetched successfully for role '{role}'", response)
    except Exception as ex:
        return _server_error(ota_db, ex, "Error@get_permissions_by_role")
    finally:
        ota_db.close()


async def update_role_permissions(request: Request, role: str, payload: RolePermissionUpdate, ota_db: Session) -> dict:
    try:
        permission_check = await require_permission(request, MANAGE_PERMISSION)
        if permission_check:
            return permission_check

        role_permissions_data = load_permissions('role') or {}
        permissions_to_save = payload.permissions.copy()
        # Admins must keep the right to manage permissions, or nobody could undo a mistake
        if role.lower() in _ADMIN_ROLES and MANAGE_PERMISSION not in permissions_to_save:
            permissions_to_save.append(MANAGE_PERMISSION)
        role_permissions_data[role.lower()] = permissions_to_save

        try:
            _save_role_permissions(role_permissions_data)
        except Exception as file_ex:
            write_log("Error@update_role_permissions_file", get_error_info(file_ex))
            return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                                   "Failed to save role permissions to file.", {}, str(file_ex))

        return common_response(http_status.HTTP_200_OK, f"Permissions updated successfully for role '{role}'",
                               {"role": role, "permissions": payload.permissions})
    except Exception as ex:
        return _server_error(ota_db, ex, "Error@update_role_permissions")
    finally:
        ota_db.close()
