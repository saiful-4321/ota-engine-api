from . import *
from fastapi import APIRouter, Depends, Request, HTTPException, status, Query
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import select
from app.models.otadb.User import User
from app.models.otadb.IPWhitelist import IPWhitelist

from app.models.enums import UserRoleEnum
from app.models.schemas import IPWhitelistSchema
from app.services.customPagination import custom_paginate
from app.helpers.exceptions import handle_exceptions
from app.utils.permission_helper import require_permission

router = APIRouter()

VALID_TYPES = ["user"]

def ensure_admin(user_role):
    if user_role.lower() != "admin":
        return False
    return True

@router.post("/create")
async def add_ip(
    request: Request,
    input: IPWhitelistSchema,
    db: Session = Depends(get_ota_db_session),
):
    try:
        # Permission check
        permission_check = await require_permission(request, "create_ip_whitelist")
        if permission_check:
            return permission_check

        # Get authenticated user
        auth_user = request.state.user
       
        # Check for duplicate IP for same entity
        existing_ip = db.query(IPWhitelist).filter(
            IPWhitelist.entity_type == input.entity_type,
            IPWhitelist.entity_id == input.entity_id,
            IPWhitelist.ip_address == input.ip_address
        ).first()
        if existing_ip:
            return common_response(status.HTTP_400_BAD_REQUEST, IP_ALREADY_EXISTS_FOR_ENTIRY, {})

        # Create new whitelist entry
        new_ip = IPWhitelist(
            ip_address=input.ip_address,
            entity_type=input.entity_type,
            entity_id=input.entity_id,
            description=input.description,
            is_active=input.is_active,
            created_by=auth_user.id,
            updated_by=auth_user.id
        )
        db.add(new_ip)
        db.commit()
        db.refresh(new_ip)

        return common_response(status.HTTP_201_CREATED, SUCCESS, new_ip)

    except SQLAlchemyError as e:
        db.rollback()
        write_log(get_error_info(e), '/whitelist/create')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        db.rollback()
        write_log(get_error_info(ex), '/whitelist/create')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        db.close()

@router.put("/update/{id}")
async def update_whitelist_by_id(
    id: int,
    input: IPWhitelistSchema,
    request: Request,
    db: Session = Depends(get_ota_db_session),
):
    try:
        # Permission check
        permission_check = await require_permission(request, "update_ip_whitelist")
        if permission_check:
            return permission_check

        # Get authenticated user
        auth_user = request.state.user

        # Fetch the whitelist entry
        ip_entry = db.query(IPWhitelist).filter(IPWhitelist.id == id).first()
        if not ip_entry:
            return common_response(status.HTTP_404_NOT_FOUND, IP_NOT_REGISTERED_FOR_ENTIRY, {})

        # Update fields if provided
        for field in ["ip_address", "entity_type", "entity_id", "description", "is_active"]:
            value = getattr(input, field, None)
            if value is not None:
                setattr(ip_entry, field, value)

        ip_entry.updated_by = auth_user.id
        db.commit()
        db.refresh(ip_entry)

        return common_response(status.HTTP_200_OK, "IP whitelist updated successfully", ip_entry)

    except SQLAlchemyError as e:
        db.rollback()
        write_log(get_error_info(e), '/whitelist/update')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        db.rollback()
        write_log(get_error_info(ex), '/whitelist/update')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        db.close()


@router.delete("/delete/{whitelist_id}")
async def remove_ip(whitelist_id: int, request: Request, db: Session = Depends(get_ota_db_session)):
    try:
        # Check permission
        permission_check = await require_permission(request, "delete_ip_whitelist")
        if permission_check:
            return permission_check

        # Fetch the IP whitelist entry
        ip_entry = db.query(IPWhitelist).filter(IPWhitelist.id == whitelist_id).first()
        if not ip_entry:
            return common_response(status.HTTP_404_NOT_FOUND, IP_NOT_REGISTERED_FOR_ENTIRY, {})

        # Delete the entry
        db.delete(ip_entry)
        db.commit()

        return common_response(status.HTTP_200_OK, "IP removed successfully", {})

    except Exception as ex:
        db.rollback()
        write_log("Error@remove_ip", get_error_info(ex))
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    
    finally:
        db.close()


# Used when you want to view all whitelisted IPs of one specific PSP or other entity if available
@router.get("/list-whitelist/{entity_type}/{entity_id}")
@handle_exceptions()
def list_whitelisted_ips(entity_type: str, entity_id: int, request: Request, db: Session = Depends(get_ota_db_session)):
    auth_user = request.state.user
    user_info = db.query(Users).filter(Users.username == auth_user.username).first()
    if not user_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    
    is_authorized = ensure_admin(user_info.user_role)
    if not is_authorized:
        return common_response(status.HTTP_403_FORBIDDEN, UNAUTHORAZED, {})

    whitelisted_ips = db.query(IPWhitelist).filter(
        IPWhitelist.entity_type == entity_type,
        IPWhitelist.entity_id == entity_id
    ).all()
    return common_response(status.HTTP_200_OK, SUCCESS, whitelisted_ips)

# when you want to list all PSP IP whitelists in one table
@router.get("/list-by-type/{entity_type}")
async def list_whitelist_by_type(
    entity_type: str,
    request: Request,
    ip_address: Optional[str] = Query(None, description="Filter by IP address"),
    entity_id: Optional[int] = Query(None, description="Filter by entity ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_ota_db_session),
):
    try:
        # Permission check
        permission_check = await require_permission(request, "view_ip_whitelist")
        if permission_check:
            return permission_check

        # Validate entity type
        if entity_type not in VALID_TYPES:
            return common_response(
                status.HTTP_400_BAD_REQUEST,
                f"Invalid entity_type: {entity_type}. Must be one of {VALID_TYPES}",
                {}
            )

        # Aliased users for created_by / updated_by
        creator = aliased(Users)
        updator = aliased(Users)

        # Build query
        query = select([
            IPWhitelist.id,
            IPWhitelist.ip_address,
            IPWhitelist.entity_type,
            IPWhitelist.entity_id,
            IPWhitelist.description,
            IPWhitelist.is_active,
            IPWhitelist.created_by,
            IPWhitelist.updated_by,
            IPWhitelist.created_at,
            IPWhitelist.updated_at,
            creator.name.label('created_by'),
            updator.name.label('updated_by')
        ]).outerjoin(
            creator, IPWhitelist.created_by == creator.id
        ).outerjoin(
            updator, IPWhitelist.updated_by == updator.id
        ).where(IPWhitelist.entity_type == entity_type)

        if ip_address is not None:
            query = query.where(IPWhitelist.ip_address == ip_address)
        if entity_id is not None:
            query = query.where(IPWhitelist.entity_id == entity_id)
        if is_active is not None:
            query = query.where(IPWhitelist.is_active == is_active)

        # Paginate results
        paginated = custom_paginate(request, query, db, 'list')
        items = paginated["list"]

        enriched_items = [dict(item, entity_name=None) for item in items]
        paginated["list"] = enriched_items

        return common_response(status.HTTP_200_OK, SUCCESS, paginated)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), '/whitelist/list-by-type')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), '/whitelist/list-by-type')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        db.close()

