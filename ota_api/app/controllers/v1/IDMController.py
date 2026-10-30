from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.helpers import exports
from app.helpers.common import get_ota_db_session

# Workflows live in app/helpers/exports.py.
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@router.get("/list")
async def idm_list(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    title: str = Query("", description="Filter by title"),
    created_at: str = Query("", description="Filter by created_at (YYYY-MM-DD)"),
    updated_at: str = Query("", description="Filter by updated_at (YYYY-MM-DD)"),
):
    # page / limit are read by the paginator from the query string
    return await exports.list_exports(request, ota_db, sort_by, sort_order, title, created_at, updated_at)


@router.get("/{file_name}")
async def download_export_file(
    file_name: str,
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
):
    return exports.download_export(file_name, ota_db)
