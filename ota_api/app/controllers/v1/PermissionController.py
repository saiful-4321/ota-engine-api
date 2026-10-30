from fastapi import APIRouter, Body, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.helpers import permissions
from app.helpers.common import get_ota_db_session
from app.models.schemas import RolePermissionUpdate

# Workflows live in app/helpers/permissions.py.
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@router.get("/{role}")
async def get_permissions_by_role(
    role: str,
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
):
    return await permissions.get_role_permissions(request, role, ota_db)


@router.post("/update/{role}")
async def update_role_permissions(
    role: str,
    request: Request,
    payload: RolePermissionUpdate = Body(...),
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
):
    return await permissions.update_role_permissions(request, role, payload, ota_db)
