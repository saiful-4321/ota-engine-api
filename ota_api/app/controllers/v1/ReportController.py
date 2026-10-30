from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.helpers import reports
from app.helpers.common import get_ota_db_session

# Workflows live in app/helpers/reports.py. page / limit are read by the paginator from the query string.
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@router.get('/users-list')
async def get_user_list(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    user_id: str = Query(None),
    name: str = Query(None),
    username: str = Query(None),
    email: str = Query(None),
    mobile: str = Query(None),
    status: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
):
    filters = {"user_id": user_id, "name": name, "username": username, "email": email, "mobile": mobile, "status": status}
    return await reports.users_report(request, ota_db, filters, start_date, end_date, sort_by, sort_order)


@router.get("/user/{user_id}")
async def get_user_details(
    user_id: str,
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
):
    return reports.user_details(user_id, ota_db)


@router.get("/api-logs")
async def get_api_logs(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    method: str = Query(None),
    url: str = Query(None),
    client_ip: str = Query(None),
    status_code: int = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    sort_by: str = Query("timestamp"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100)
):
    filters = {"method": method, "url": url, "client_ip": client_ip, "status_code": status_code}
    return await reports.api_logs(request, ota_db, filters, start_date, end_date, sort_by, sort_order)


@router.get("/api-log/{log_id}")
async def get_api_log_details(log_id: int = Path(...), ota_db: Session = Depends(get_ota_db_session)):
    return reports.api_log_details(log_id, ota_db)


@router.get("/callback-api-logs")
async def get_callback_api_logs(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    source: str = Query(None),
    log_source: str = Query(None),
    url: str = Query(None),
    response_status: int = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    sort_by: str = Query("timestamp"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100)
):
    filters = {"source": source, "log_source": log_source, "url": url, "response_status": response_status}
    return await reports.callback_api_logs(request, ota_db, filters, start_date, end_date, sort_by, sort_order)


@router.get("/callback-api-log/{log_id}")
async def get_callback_api_log_details(log_id: int = Path(...), ota_db: Session = Depends(get_ota_db_session)):
    return reports.callback_api_log_details(log_id, ota_db)


@router.get("/flight-search-logs")
async def get_flight_search_logs(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    supplier: str = Query(None),
    origin: str = Query(None),
    destination: str = Query(None),
    user_id: str = Query(None),
    status: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100)
):
    filters = {"supplier": supplier, "origin": origin, "destination": destination, "user_id": user_id, "status": status}
    return reports.flight_search_logs(request, ota_db, filters, start_date, end_date, sort_by, sort_order)


@router.get("/flight-search-log/{search_id}")
async def get_flight_search_log_details(
    search_id: str = Path(..., description="The search_id (UUID) or internal ID"),
    ota_db: Session = Depends(get_ota_db_session),
):
    return reports.flight_search_log_details(search_id, ota_db)


@router.get("/bookings")
async def get_bookings_list(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    pnr: str = Query(None),
    user_id: str = Query(None),
    booking_status: str = Query(None),
    payment_status: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100)
):
    filters = {"pnr": pnr, "user_id": user_id, "booking_status": booking_status, "payment_status": payment_status}
    return reports.bookings(request, ota_db, filters, start_date, end_date, sort_by, sort_order)


@router.get("/booking/{booking_id}")
async def get_booking_details(booking_id: str = Path(...), ota_db: Session = Depends(get_ota_db_session)):
    return reports.booking_details(booking_id, ota_db)
