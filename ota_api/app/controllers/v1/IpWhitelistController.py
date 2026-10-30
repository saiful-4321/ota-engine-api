from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.helpers import ip_whitelist
from app.helpers.common import get_ota_db_session
from app.models.schemas import IPWhitelistSchema

# Workflows live in app/helpers/ip_whitelist.py.
router = APIRouter()


@router.post("/create")
async def add_ip(request: Request, input: IPWhitelistSchema, db: Session = Depends(get_ota_db_session)):
    return await ip_whitelist.add_ip(request, input, db)


@router.put("/update/{id}")
async def update_whitelist_by_id(id: int, input: IPWhitelistSchema, request: Request, db: Session = Depends(get_ota_db_session)):
    return await ip_whitelist.update_ip(request, id, input, db)


@router.delete("/delete/{whitelist_id}")
async def remove_ip(whitelist_id: int, request: Request, db: Session = Depends(get_ota_db_session)):
    return await ip_whitelist.remove_ip(request, whitelist_id, db)


# All whitelisted IPs of one specific entity (e.g. one PSP)
@router.get("/list-whitelist/{entity_type}/{entity_id}")
def list_whitelisted_ips(entity_type: str, entity_id: int, request: Request, db: Session = Depends(get_ota_db_session)):
    return ip_whitelist.list_entity_ips(request, entity_type, entity_id, db)


# All whitelists of one entity type in one table
@router.get("/list-by-type/{entity_type}")
async def list_whitelist_by_type(
    entity_type: str,
    request: Request,
    ip_address: Optional[str] = Query(None, description="Filter by IP address"),
    entity_id: Optional[int] = Query(None, description="Filter by entity ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_ota_db_session),
):
    return await ip_whitelist.list_by_type(request, entity_type, db, ip_address, entity_id, is_active)
