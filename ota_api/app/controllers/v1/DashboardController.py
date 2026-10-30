from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.helpers import dashboard
from app.helpers.common import get_ota_db_session

# Workflows live in app/helpers/dashboard.py.
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@router.get('/statistics/summary')
async def get_summary_statistics(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme)
):
    return await dashboard.summary_statistics(request, ota_db)


@router.get('/statistics/historical-users')
async def get_historical_users_statistics(
    request: Request,
    duration: str = Query("1y", regex="^(1m|3m|4m|6m|1y)$"),
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme)
):
    return await dashboard.historical_users_statistics(request, duration, ota_db)
