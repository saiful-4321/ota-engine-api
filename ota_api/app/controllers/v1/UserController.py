from . import *
from sqlalchemy.orm import Session, aliased
from fastapi import APIRouter, status as httpStatus, Depends, Request, Query, Path
from fastapi.security import OAuth2PasswordBearer
from app.models.otadb.User import User
# from app.models.otadb.PSPProfile import PSPProfile
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.services.customPagination import custom_paginate
from datetime import datetime
import uuid
from typing import Optional
from app.models.schemas import UserSchema
from app.helpers.password_utils import hash_password
from app.utils.permission_helper import require_permission

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

ALLOWED_USER_TYPES = ["admin", "super_admin"]
ALLOWED_DELETE_TYPES = ["admin", "super_admin", "back_office"]

def is_authorized(user, action: str = "manage"):
    if action == "delete":
        return user and user.user_role in ALLOWED_DELETE_TYPES
    return user and user.user_role in ALLOWED_USER_TYPES

def build_user_query(
    db: Session,
    entity_type: Optional[str],
    filters: dict
):
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

    # Conditional join and selection of entity_name and entity_short_name
    # if entity_type == 'psp':
    #     query = query.add_columns(
    #         PSPProfile.name.label('entity_name'),
    #         PSPProfile.short_name.label('entity_short_name')
    #     ).outerjoin(
    #         PSPProfile, Users.entity_id == PSPProfile.id
    #     )
    # elif entity_type == 'broker':
    #     query = query.add_columns(
    #         BrokerProfile.name.label('entity_name'),
    #         BrokerProfile.short_name.label('entity_short_name')
    #     ).outerjoin(
    #         BrokerProfile, Users.entity_id == BrokerProfile.id
    #     )
    # else:
    #     from sqlalchemy.sql import literal_column
    #     query = query.add_columns(
    #         literal_column("NULL").label("entity_name"),
    #         literal_column("NULL").label("entity_short_name")
    #     )

    # Joins for creator/updator names
    query = query.outerjoin(creator, Users.created_by == creator.id)
    query = query.outerjoin(updator, Users.updated_by == updator.id)

    # Filters
    if filters.get("name"):
        query = query.filter(Users.name.ilike(f"%{filters['name']}%"))
    if filters.get("username"):
        query = query.filter(Users.username.ilike(f"%{filters['username']}%"))
    if filters.get("email"):
        query = query.filter(Users.email.ilike(f"%{filters['email']}%"))
    if filters.get("mobile"):
        query = query.filter(Users.mobile.ilike(f"%{filters['mobile']}%"))
    if filters.get("user_role"):
        query = query.filter(Users.user_role.ilike(f"%{filters['user_role']}%"))
    if filters.get("entity_type"):
        query = query.filter(Users.entity_type.ilike(f"%{filters['entity_type']}%"))
    if filters.get("entity_id"):
        query = query.filter(Users.entity_id == filters['entity_id'])
    if filters.get("status") is not None:
        query = query.filter(Users.status == (filters['status'].lower() == 'true'))

    return query.order_by(Users.name.asc())


@router.get('/list')
# @router.get('/list-by-type/{entity_type}')
async def get_user_list(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    entity_type: Optional[str] = Query(None, description="Type of entity (e.g., 'PSP', 'Broker')"),
    name: str = Query(None),
    username: str = Query(None),
    email: str = Query(None),
    mobile: str = Query(None),
    user_role: str = Query(None),
    entity_id: str = Query(None),
    status: str = Query(None),
    token: str = Depends(oauth2_scheme),
):
    try:
        if entity_type is None:
            return common_response(httpStatus.HTTP_400_BAD_REQUEST, "Query parameter 'entity_type' is required. Please provide an entity type")

        permission_name = f"view_{entity_type.lower()}_users"

        permission_check = await require_permission(request, permission_name)
        if permission_check:
            return permission_check

        filters = {
            "name": name,
            "username": username,
            "email": email,
            "mobile": mobile,
            "user_role": user_role,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "status": status
        }

        query = build_user_query(ota_db, entity_type, filters)

        data = custom_paginate(request, query, ota_db, 'list')
        msg = f"Users{' for entity type ' + entity_type if entity_type else ''} retrieved successfully"
        return common_response(httpStatus.HTTP_200_OK, msg, data)

    except SQLAlchemyError as e:
        path = f"/users/list-by-type/{entity_type}" if entity_type else "/users/list"
        write_log(get_error_info(e), path)
        return common_response(httpStatus.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        path = f"/users/list-by-type/{entity_type}" if entity_type else "/users/list"
        write_log(get_error_info(ex), path)
        return common_response(httpStatus.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()


@router.post("/create")
async def create_user(
    request: Request,
    input: UserSchema,
    ota_db: Session = Depends(get_ota_db_session),
):
    try:
        user_type = input.user_role.lower()
        permission_name = f"create_{user_type}_user"

        permission_check = await require_permission(request, permission_name)
        if permission_check:
            return permission_check

        if not input.password:
            return common_response(httpStatus.HTTP_400_BAD_REQUEST, "Password is required for creating a user")

        current_user = request.state.user

        new_user = Users(
            user_id=uuid.uuid4(),
            name=input.name,
            username=input.username,
            email=input.email,
            mobile=input.mobile,
            password=hash_password(input.password),  # Hash password
            user_role=input.user_role,
            entity_type=input.entity_type,
            entity_id=input.entity_id,
            status=input.status,
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        ota_db.add(new_user)
        ota_db.commit()
        ota_db.refresh(new_user)
        # Exclude sensitive fields from response
        response_data = {
            "id": new_user.id,
            "user_id": str(new_user.user_id),
            "name": new_user.name,
            "username": new_user.username,
            "email": new_user.email,
            "mobile": new_user.mobile,
            "user_role": new_user.user_role,
            "entity_type": new_user.entity_type,
            "entity_id": new_user.entity_id,
            "status": new_user.status,
            "created_at": new_user.created_at,
            "updated_at": new_user.updated_at,
            "created_by": new_user.created_by,
            "updated_by": new_user.updated_by,
            "created_by_name": new_user.creator.name if new_user.creator else None,
            "updated_by_name": new_user.updater.name if new_user.updater else None
        }
        return common_response(httpStatus.HTTP_200_OK, "User created successfully", response_data)
    except IntegrityError as iex:
        ota_db.rollback()
        write_log("Error@create_user", get_error_info(iex))
        return common_response(httpStatus.HTTP_400_BAD_REQUEST, "Duplicate entry: username or email already exists", {}, iex)
    except Exception as ex:
        ota_db.rollback()
        write_log("Error@create_user", get_error_info(ex))
        return common_response(httpStatus.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

@router.put("/update/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    input: UserSchema,
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
):
    try:
        user_type = input.user_role.lower()
        permission_name = f"update_{user_type}_user"
        permission_check = await require_permission(request, permission_name)
        if permission_check:
            return permission_check
        
        current_user = request.state.user

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
        user.updated_by = current_user.id
        user.updated_at = datetime.utcnow()

        ota_db.commit()
        ota_db.refresh(user)
        # Exclude sensitive fields from response
        response_data = {
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
            "last_login": user.last_login,
            "last_logged_ip": user.last_logged_ip,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "created_by": user.created_by,
            "updated_by": user.updated_by,
            "created_by_name": user.creator.name if user.creator else None,
            "updated_by_name": user.updater.name if user.updater else None
        }
        return common_response(httpStatus.HTTP_200_OK, "User updated successfully", response_data)
    except IntegrityError as iex:
        ota_db.rollback()
        write_log("Error@update_user", get_error_info(iex))
        return common_response(httpStatus.HTTP_400_BAD_REQUEST, "Duplicate entry: username or email already exists", {}, iex)
    except Exception as ex:
        ota_db.rollback()
        write_log("Error@update_user", get_error_info(ex))
        return common_response(httpStatus.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

@router.delete("/delete/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
):
    try:
        user = ota_db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return common_response(httpStatus.HTTP_404_NOT_FOUND, "User not found")
        
        user_type = user.user_role.lower()  
        permission_name = f"delete_{user_type}_user"
        permission_check = await require_permission(request, permission_name)
        if permission_check:
            return permission_check

        user = ota_db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return common_response(httpStatus.HTTP_404_NOT_FOUND, "User not found")

        ota_db.delete(user)
        ota_db.commit()
        return common_response(httpStatus.HTTP_200_OK, "User deleted successfully")
    except Exception as ex:
        ota_db.rollback()
        write_log("Error@delete_user", get_error_info(ex))
        return common_response(httpStatus.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()