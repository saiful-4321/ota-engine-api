from . import *
from sqlalchemy.orm import Session
from fastapi import APIRouter, status as http_status, Depends, Request, Body
from fastapi.security import OAuth2PasswordBearer
from app.helpers.common import (
    write_log,
    get_ota_db_session,
    get_error_info,
    common_response
)
from app.helpers.constants import INTERNAL_SERVER_ERROR, DATA_NOT_FOUND
from app.models.schemas import RolePermissionUpdate
from app.utils.permission_helper import require_permission, ROLE_PERMISSIONS_FILE, load_permissions


router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

@router.get("/{role}")
async def get_permissions_by_role(
    role: str,
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
):
    try:
        permission_check = await require_permission(request, "update_permissions")
        if permission_check:
            return permission_check

        all_permissions_data = load_permissions('all')
        role_permissions_data = load_permissions('role')

        active_permissions = role_permissions_data.get(role.lower(), [])

        if not all_permissions_data:
            return common_response(
                http_status.HTTP_404_NOT_FOUND,
                DATA_NOT_FOUND,
                {},
                "No permissions found in all_permissions.json"
            )

        response = {
            "all_permissions": all_permissions_data,
            "active_permissions": active_permissions
        }

        return common_response(
            http_status.HTTP_200_OK,
            f"Permissions fetched successfully for role '{role}'",
            response
        )

    except Exception as ex:
        ota_db.rollback()
        write_log("Error@get_permissions_by_role", get_error_info(ex))
        return common_response(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            INTERNAL_SERVER_ERROR,
            {},
            str(ex)
        )
    finally:
        ota_db.close()

@router.post("/update/{role}")
async def update_role_permissions(
    role: str,
    request: Request,
    payload: RolePermissionUpdate = Body(...),
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
):
    try:
        permission_check = await require_permission(request, "update_permissions")
        if permission_check:
            return permission_check

        role_permissions_data = load_permissions('role')
        if role_permissions_data is None:
            role_permissions_data = {}

        permissions_to_save = payload.permissions.copy()
        if role.lower() in ["admin", "superadmin"]:
            if "update_permissions" not in permissions_to_save:
                permissions_to_save.append("update_permissions")

        role_permissions_data[role.lower()] = permissions_to_save

        try:
            with open(ROLE_PERMISSIONS_FILE, "w") as f:
                json.dump(role_permissions_data, f, indent=4)
        except Exception as file_ex:
            write_log("Error@update_role_permissions_file", get_error_info(file_ex))
            return common_response(
                http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Failed to save role permissions to file.",
                {},
                str(file_ex)
            )

        return common_response(
            http_status.HTTP_200_OK,
            f"Permissions updated successfully for role '{role}'",
            {"role": role, "permissions": payload.permissions}
        )

    except Exception as ex:
        ota_db.rollback()
        write_log("Error@update_role_permissions", get_error_info(ex))
        return common_response(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            INTERNAL_SERVER_ERROR,
            {},
            str(ex)
        )
    finally:
        ota_db.close()
