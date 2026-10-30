from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.helpers import exports
from app.helpers.common import get_ota_db_session
from app.models.schemas import UserQueryParams

# Workflows live in app/helpers/exports.py.
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@router.post("/users")
async def export_users(
    request: Request,
    filters: UserQueryParams = Depends(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
):
    return exports.export_users(request, filters, background_tasks, ota_db)
