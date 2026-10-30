"""
app/helpers/ip_whitelist.py

Workflows behind the /ip endpoints. PSP users may only call the API from whitelisted IPs
(enforced by AuthMiddleware); these functions manage that list.

KNOWN ISSUE: the two list views join the legacy `Users` model, which is unset (see
app/helpers/users.py), so they end in the 500 branch — unchanged from the original controller.
"""

from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import select

from app.helpers.common import common_response, get_error_info, write_log
from app.helpers.constants import (
    INTERNAL_SERVER_ERROR, IP_ALREADY_EXISTS_FOR_ENTIRY, IP_NOT_REGISTERED_FOR_ENTIRY, SUCCESS, UNAUTHORAZED,
    USER_NOT_FOUND,
)
from app.helpers.users import Users  # legacy model, unset — see KNOWN ISSUE
from app.models.otadb.IPWhitelist import IPWhitelist
from app.models.schemas import IPWhitelistSchema
from app.services.customPagination import custom_paginate
from app.utils.permission_helper import require_permission

VALID_TYPES = ["user"]
_UPDATABLE_FIELDS = ["ip_address", "entity_type", "entity_id", "description", "is_active"]


def _server_error(db: Session, ex: Exception, source: str, rollback: bool = True) -> dict:
    if rollback:
        db.rollback()
    write_log(get_error_info(ex), source)
    return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)


def is_admin(user_role: str) -> bool:
    return user_role.lower() == "admin"


async def add_ip(request: Request, input: IPWhitelistSchema, db: Session) -> dict:
    try:
        permission_check = await require_permission(request, "create_ip_whitelist")
        if permission_check:
            return permission_check

        existing_ip = db.query(IPWhitelist).filter(
            IPWhitelist.entity_type == input.entity_type,
            IPWhitelist.entity_id == input.entity_id,
            IPWhitelist.ip_address == input.ip_address
        ).first()
        if existing_ip:
            return common_response(status.HTTP_400_BAD_REQUEST, IP_ALREADY_EXISTS_FOR_ENTIRY, {})

        auth_user = request.state.user
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
    except Exception as ex:
        return _server_error(db, ex, '/whitelist/create')
    finally:
        db.close()


async def update_ip(request: Request, whitelist_id: int, input: IPWhitelistSchema, db: Session) -> dict:
    try:
        permission_check = await require_permission(request, "update_ip_whitelist")
        if permission_check:
            return permission_check

        ip_entry = db.query(IPWhitelist).filter(IPWhitelist.id == whitelist_id).first()
        if not ip_entry:
            return common_response(status.HTTP_404_NOT_FOUND, IP_NOT_REGISTERED_FOR_ENTIRY, {})

        for field in _UPDATABLE_FIELDS:
            value = getattr(input, field, None)
            if value is not None:
                setattr(ip_entry, field, value)
        ip_entry.updated_by = request.state.user.id
        db.commit()
        db.refresh(ip_entry)
        return common_response(status.HTTP_200_OK, "IP whitelist updated successfully", ip_entry)
    except Exception as ex:
        return _server_error(db, ex, '/whitelist/update')
    finally:
        db.close()


async def remove_ip(request: Request, whitelist_id: int, db: Session) -> dict:
    try:
        permission_check = await require_permission(request, "delete_ip_whitelist")
        if permission_check:
            return permission_check

        ip_entry = db.query(IPWhitelist).filter(IPWhitelist.id == whitelist_id).first()
        if not ip_entry:
            return common_response(status.HTTP_404_NOT_FOUND, IP_NOT_REGISTERED_FOR_ENTIRY, {})

        db.delete(ip_entry)
        db.commit()
        return common_response(status.HTTP_200_OK, "IP removed successfully", {})
    except Exception as ex:
        db.rollback()
        write_log("Error@remove_ip", get_error_info(ex))
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        db.close()


def list_entity_ips(request: Request, entity_type: str, entity_id: int, db: Session) -> dict:
    """All IPs of one entity (admins only)."""
    try:
        user_info = db.query(Users).filter(Users.username == request.state.user.username).first()
        if not user_info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
        if not is_admin(user_info.user_role):
            return common_response(status.HTTP_403_FORBIDDEN, UNAUTHORAZED, {})

        whitelisted_ips = db.query(IPWhitelist).filter(
            IPWhitelist.entity_type == entity_type,
            IPWhitelist.entity_id == entity_id
        ).all()
        return common_response(status.HTTP_200_OK, SUCCESS, whitelisted_ips)
    except HTTPException as ex:
        return _server_error(db, ex, str(request.url), rollback=False)
    except Exception as ex:
        return _server_error(db, ex, str(request.url))
    finally:
        db.close()


async def list_by_type(request: Request, entity_type: str, db: Session, ip_address: Optional[str] = None,
                       entity_id: Optional[int] = None, is_active: Optional[bool] = None) -> dict:
    """All IPs of an entity type, with creator/updater names, paginated."""
    try:
        permission_check = await require_permission(request, "view_ip_whitelist")
        if permission_check:
            return permission_check

        if entity_type not in VALID_TYPES:
            return common_response(
                status.HTTP_400_BAD_REQUEST,
                f"Invalid entity_type: {entity_type}. Must be one of {VALID_TYPES}",
                {}
            )

        creator = aliased(Users)
        updator = aliased(Users)
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

        paginated = custom_paginate(request, query, db, 'list')
        paginated["list"] = [dict(item, entity_name=None) for item in paginated["list"]]
        return common_response(status.HTTP_200_OK, SUCCESS, paginated)
    except Exception as ex:
        return _server_error(db, ex, '/whitelist/list-by-type', rollback=False)
    finally:
        db.close()
