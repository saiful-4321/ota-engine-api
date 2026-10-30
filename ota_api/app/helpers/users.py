"""
app/helpers/users.py

Workflows behind the /users endpoints (back-office user management). Each action is gated by a
permission named after the target user's role, e.g. `create_admin_user`.

KNOWN ISSUE: these workflows were written against the legacy `Users` model (user_id UUID,
mobile, user_role, entity_type, status bool …), which no longer matches the `users` table. See
`Users` below. Port them to app.models.otadb.User.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import Request, status as httpStatus
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.helpers.common import common_response, get_error_info, write_log
from app.helpers.constants import INTERNAL_SERVER_ERROR
from app.utils.password_utils import hash_password
from app.models.schemas import UserSchema
from app.services.customPagination import custom_paginate
from app.utils.permission_helper import require_permission

# Legacy model these workflows (and the user parts of dashboard, exports, ip_whitelist and reports)
# were written for. It cannot be imported — app/models/otadb/_Users.py redefines the `users` table
# already mapped by app.models.otadb.User — so it is unset and every call ends in the 500 branch,
# exactly as before the controllers were split.
Users = None

DUPLICATE_USER = "Duplicate entry: username or email already exists"
_TEXT_FILTERS = ("name", "username", "email", "mobile", "user_role", "entity_type")


# ── Queries & serialization ──────────────────────────────────────────────────

def build_user_query(db: Session, filters: dict):
    creator = aliased(Users)
    updator = aliased(Users)

    query = db.query(
        Users.id,
        Users.user_id,
        Users.name,
        Users.username,
        Users.email,
        Users.mobile,
        Users.user_role,
        Users.entity_type,
        Users.entity_id,
        Users.status,
        Users.last_login,
        Users.last_logged_ip,
        Users.created_at,
        Users.updated_at,
        creator.name.label('created_by_name'),
        updator.name.label('updated_by_name'),
    )
    query = query.outerjoin(creator, Users.created_by == creator.id)
    query = query.outerjoin(updator, Users.updated_by == updator.id)

    for field in _TEXT_FILTERS:
        if filters.get(field):
            query = query.filter(getattr(Users, field).ilike(f"%{filters[field]}%"))
    if filters.get("entity_id"):
        query = query.filter(Users.entity_id == filters['entity_id'])
    if filters.get("status") is not None:
        query = query.filter(Users.status == (filters['status'].lower() == 'true'))

    return query.order_by(Users.name.asc())


def serialize_user(user, include_login: bool = False) -> dict:
    """User as returned to the client — never includes the password."""
    data = {
        "id": user.id,
        "user_id": str(user.user_id),
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "mobile": user.mobile,
        "user_role": user.user_role,
        "entity_type": user.entity_type,
        "entity_id": user.entity_id,
        "status": user.status,
    }
    if include_login:
        data.update({"last_login": user.last_login, "last_logged_ip": user.last_logged_ip})
    data.update({
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "created_by": user.created_by,
        "updated_by": user.updated_by,
        "created_by_name": user.creator.name if user.creator else None,
        "updated_by_name": user.updater.name if user.updater else None,
    })
    return data


# ── Endpoint workflows ───────────────────────────────────────────────────────

async def list_users(request: Request, ota_db: Session, entity_type: Optional[str], filters: dict) -> dict:
    try:
        if entity_type is None:
            return common_response(httpStatus.HTTP_400_BAD_REQUEST, "Query parameter 'entity_type' is required. Please provide an entity type")

        permission_check = await require_permission(request, f"view_{entity_type.lower()}_users")
        if permission_check:
            return permission_check

        query = build_user_query(ota_db, {**filters, "entity_type": entity_type})
        data = custom_paginate(request, query, ota_db, 'list')
        msg = f"Users{' for entity type ' + entity_type if entity_type else ''} retrieved successfully"
        return common_response(httpStatus.HTTP_200_OK, msg, data)
    except Exception as ex:
        path = f"/users/list-by-type/{entity_type}" if entity_type else "/users/list"
        write_log(get_error_info(ex), path)
        return common_response(httpStatus.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()


async def create_user(request: Request, input: UserSchema, ota_db: Session) -> dict:
    try:
        permission_check = await require_permission(request, f"create_{input.user_role.lower()}_user")
        if permission_check:
            return permission_check

        if not input.password:
            return common_response(httpStatus.HTTP_400_BAD_REQUEST, "Password is required for creating a user")

        new_user = Users(
            user_id=uuid.uuid4(),
            name=input.name,
            username=input.username,
            email=input.email,
            mobile=input.mobile,
            password=hash_password(input.password),
            user_role=input.user_role,
            entity_type=input.entity_type,
            entity_id=input.entity_id,
            status=input.status,
            created_by=request.state.user.id,
            created_at=datetime.utcnow()
        )
        ota_db.add(new_user)
        ota_db.commit()
        ota_db.refresh(new_user)
        return common_response(httpStatus.HTTP_200_OK, "User created successfully", serialize_user(new_user))
    except IntegrityError as iex:
        ota_db.rollback()
        write_log("Error@create_user", get_error_info(iex))
        return common_response(httpStatus.HTTP_400_BAD_REQUEST, DUPLICATE_USER, {}, iex)
    except Exception as ex:
        ota_db.rollback()
        write_log("Error@create_user", get_error_info(ex))
        return common_response(httpStatus.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()


async def update_user(request: Request, user_id: uuid.UUID, input: UserSchema, ota_db: Session) -> dict:
    try:
        permission_check = await require_permission(request, f"update_{input.user_role.lower()}_user")
        if permission_check:
            return permission_check

        user = ota_db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return common_response(httpStatus.HTTP_404_NOT_FOUND, "User not found")

        user.name = input.name
        user.username = input.username
        user.email = input.email
        user.mobile = input.mobile
        if input.password:  # Update password only if provided
            user.password = hash_password(input.password)
        user.user_role = input.user_role
        user.entity_type = input.entity_type
        user.entity_id = input.entity_id
        user.status = input.status
        user.updated_by = request.state.user.id
        user.updated_at = datetime.utcnow()

        ota_db.commit()
        ota_db.refresh(user)
        return common_response(httpStatus.HTTP_200_OK, "User updated successfully", serialize_user(user, include_login=True))
    except IntegrityError as iex:
        ota_db.rollback()
        write_log("Error@update_user", get_error_info(iex))
        return common_response(httpStatus.HTTP_400_BAD_REQUEST, DUPLICATE_USER, {}, iex)
    except Exception as ex:
        ota_db.rollback()
        write_log("Error@update_user", get_error_info(ex))
        return common_response(httpStatus.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()


async def delete_user(request: Request, user_id: uuid.UUID, ota_db: Session) -> dict:
    try:
        user = ota_db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return common_response(httpStatus.HTTP_404_NOT_FOUND, "User not found")

        permission_check = await require_permission(request, f"delete_{user.user_role.lower()}_user")
        if permission_check:
            return permission_check

        ota_db.delete(user)
        ota_db.commit()
        return common_response(httpStatus.HTTP_200_OK, "User deleted successfully")
    except Exception as ex:
        ota_db.rollback()
        write_log("Error@delete_user", get_error_info(ex))
        return common_response(httpStatus.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()
