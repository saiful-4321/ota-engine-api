from . import *
from sqlalchemy import asc, desc, func, case
from sqlalchemy.orm import Session
from fastapi import APIRouter, status as http_status, Depends, Query, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from app.models.otadb.User import User
from app.models.otadb.CallbackApiLog import CallbackApiLog
from app.models.otadb.APILog import APILog
from app.services.customPagination import custom_paginate
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from fastapi import Path
from app.utils.permission_helper import require_permission
from app.models.otadb.SearchRequest import SearchRequest
from app.models.otadb.Booking import Booking
from app.models.otadb.BookingSegment import BookingSegment
from app.models.otadb.BookingPassenger import BookingPassenger
from app.models.otadb.Ticket import Ticket
from app.models.otadb.Supplier import Supplier
from app.models.otadb.Payment import Payment
from app.models.otadb.Refund import Refund
from app.models.otadb.BookingStatusHistory import BookingStatusHistory
from app.models.otadb.SupplierLog import SupplierLog
import asyncio
import uuid

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
    try:
        
        permission_check = await require_permission(request, "view_dashboard_analytics")

        # If permission fails, block access
        if permission_check:
            return permission_check
        
        valid_sort_columns = {
            "id": Users.id,
            "user_id": Users.user_id,
            "name": Users.name,
            "username": Users.username,
            "email": Users.email,
            "mobile": Users.mobile,
            "status": Users.status,
            "created_at": Users.created_at,
        }

        sort_by = sort_by.strip() if sort_by and sort_by.strip() else "created_at"
        sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else "desc"

        if sort_by not in valid_sort_columns:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_by field", {})
        if sort_order not in ["asc", "desc"]:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_order value", {})

        # Base query with filters
        base_query = ota_db.query(Users)

        if user_id:
             try:
                valid_uuid = uuid.UUID(user_id)
                base_query = base_query.filter(Users.user_id == valid_uuid)
             except ValueError:
                pass # Invalid UUID, return nothing or ignore? currently ignoring by not filtering, effectively returning all if other filters don't apply, or should it return empty?
                # Usually if ID is provided but invalid format, return empty.
                # return common_response(http_status.HTTP_200_OK, SUCCESS, {"data": [], "total": 0})
        
        if name and name.strip():
            base_query = base_query.filter(Users.name.ilike(f"%{name.strip()}%"))
        if username and username.strip():
            base_query = base_query.filter(Users.username.ilike(f"%{username.strip()}%"))
        if email and email.strip():
            base_query = base_query.filter(Users.email.ilike(f"%{email.strip()}%"))
        if mobile and mobile.strip():
            base_query = base_query.filter(Users.mobile.ilike(f"%{mobile.strip()}%"))
        
        if status and status.strip():
             if status.lower() == 'active':
                base_query = base_query.filter(Users.status == True)
             elif status.lower() == 'inactive':
                base_query = base_query.filter(Users.status == False)

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                base_query = base_query.filter(Users.created_at >= start_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid start_date format. Use YYYY-MM-DD.", {})

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                base_query = base_query.filter(Users.created_at <= end_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid end_date format. Use YYYY-MM-DD.", {})

        # Aggregate calculation (Total Users matching filter)
        total_count = base_query.with_entities(func.count()).scalar()
        
        # Define columns for data fetch
        data_query = base_query.with_entities(
            Users.id,
            Users.user_id,
            Users.name,
            Users.username,
            Users.email,
            Users.mobile,
            Users.status,
            Users.created_at,
        )

        # Apply sorting
        sort_column = valid_sort_columns[sort_by]
        data_query = data_query.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

        # Paginate the data
        paginated_data = custom_paginate(request, data_query, ota_db)

        # Final response
        response = {
            "summary": {
                "total_count": total_count,
            },
            **paginated_data  # includes list, page, limit, etc.
        }

        return common_response(http_status.HTTP_200_OK, SUCCESS, response)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), '/users-list')
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), '/users-list')
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()


@router.get("/user/{user_id}")
async def get_user_details(
    user_id: str,
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
):
    try:
        # Validate UUID
        try:
            valid_uuid = uuid.UUID(user_id)
        except ValueError:
             return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid user_id format", {})

        user = ota_db.query(Users).filter(Users.user_id == valid_uuid).first()

        if not user:
            return common_response(http_status.HTTP_404_NOT_FOUND, DATA_NOT_FOUND, {})

        response = {
            "id": user.id,
            "user_id": str(user.user_id),
            "name": user.name,
            "username": user.username,
            "email": user.email,
            "mobile": user.mobile,
            "status": user.status,
            "created_at": user.created_at,
            # Add other fields if needed from Users model
        }

        return common_response(http_status.HTTP_200_OK, SUCCESS, response)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), f'/user/{user_id}')
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except HTTPException as he:
        raise he
    except Exception as ex:
        write_log(get_error_info(ex), f'/user/{user_id}')
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

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
    try:
        permission_check = await require_permission(request, "view_api_logs")
        if permission_check:
            return permission_check
        
        valid_sort_columns = {
            "id": APILog.id,
            "timestamp": APILog.timestamp,
            "method": APILog.method,
            "url": APILog.url,
            "client_ip": APILog.client_ip,
            "response_status": APILog.response_status,
            "process_time": APILog.process_time,
        }

        sort_by = sort_by.strip() if sort_by and sort_by.strip() else "timestamp"
        sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else "desc"

        if sort_by not in valid_sort_columns:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_by field", {})
        if sort_order not in ["asc", "desc"]:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_order value", {})

        # === Base Query with Filters ===
        query = ota_db.query(APILog.id, APILog.timestamp, APILog.method, APILog.url, APILog.client_ip, APILog.headers, APILog.query_params, APILog.request_body, APILog.user_agent, APILog.response_status, APILog.response_size, APILog.response_body, APILog.process_time, APILog.raw_request_body, APILog.error_message, APILog.error_details, APILog.username)

        if method and method.strip():
            query = query.filter(APILog.method.ilike(f"%{method.strip()}%"))
        if url and url.strip():
            query = query.filter(APILog.url.ilike(f"%{url.strip()}%"))
        if client_ip and client_ip.strip():
            query = query.filter(APILog.client_ip.ilike(f"%{client_ip.strip()}%"))
        if status_code:
            query = query.filter(APILog.response_status == status_code)
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(APILog.timestamp >= start_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid start_date format. Use YYYY-MM-DD.", {})
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                query = query.filter(APILog.timestamp <= end_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid end_date format. Use YYYY-MM-DD.", {})

        # === Summary Aggregates ===
        summary_data = query.with_entities(
            func.count().label("total_logs"),
            func.sum(case((APILog.response_status < 400, 1), else_=0)).label("success_logs"),
            func.sum(case((APILog.response_status >= 400, 1), else_=0)).label("failed_logs"),
            func.coalesce(func.avg(APILog.process_time), 0).label("avg_response_time")
        ).first()

        # === Sorting ===
        sort_column = valid_sort_columns[sort_by]
        query = query.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

        # === Pagination ===
        paginated_data = custom_paginate(request, query, ota_db)
        # === Final Response ===
        response = {
            "summary": {
                "total_count": summary_data.total_logs,
                "success_count": summary_data.success_logs,
                "failed_count": summary_data.failed_logs,
                "avg_response_time": round(float(summary_data.avg_response_time), 4),
            },
            **paginated_data
        }

        return common_response(http_status.HTTP_200_OK, SUCCESS, response)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), "/api-logs")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), "/api-logs")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

@router.get("/api-log/{log_id}")
async def get_api_log_details(
    log_id: int = Path(...),
    ota_db: Session = Depends(get_ota_db_session),
):
    try:
        log = ota_db.query(APILog).filter(APILog.id == log_id).first()
        if not log:
            return common_response(http_status.HTTP_404_NOT_FOUND, DATA_NOT_FOUND, {})

        response = {
            "id": log.id,
            "timestamp": log.timestamp,
            "method": log.method,
            "url": log.url,
            "client_ip": log.client_ip,
            "headers": log.headers,
            "query_params": log.query_params,
            "request_body": log.request_body,
            "raw_request_body": log.raw_request_body,
            "user_agent": log.user_agent,
            "response_status": log.response_status,
            "response_size": log.response_size,
            "response_body": log.response_body,
            "process_time": log.process_time,
            "error_message": log.error_message,
            "error_details": log.error_details,
        }

        return common_response(http_status.HTTP_200_OK, SUCCESS, response)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), f"/api-log/{log_id}")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), f"/api-log/{log_id}")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

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
    try:
        permission_check = await require_permission(request, "view_callback_api_logs")
        if permission_check:
            return permission_check
        
        valid_sort_columns = {
            "id": CallbackApiLog.id,
            "timestamp": CallbackApiLog.timestamp,
            "source": CallbackApiLog.source,
            "log_source": CallbackApiLog.log_source,
            "url": CallbackApiLog.url,
            "response_status": CallbackApiLog.response_status,
        }

        sort_by = sort_by.strip() if sort_by and sort_by.strip() else "timestamp"
        sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else "desc"

        if sort_by not in valid_sort_columns:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_by field", {})
        if sort_order not in ["asc", "desc"]:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_order value", {})

        # === Base Query ===
        query = ota_db.query(
            CallbackApiLog.id,
            CallbackApiLog.timestamp,
            CallbackApiLog.source,
            CallbackApiLog.log_source,
            CallbackApiLog.url,
            CallbackApiLog.request_body,
            CallbackApiLog.response_status,
            CallbackApiLog.response_message,
            CallbackApiLog.additional_info
        )

        # === Filters ===
        if source and source.strip():
            query = query.filter(CallbackApiLog.source.ilike(f"%{source.strip()}%"))
        if log_source and log_source.strip():
            query = query.filter(CallbackApiLog.log_source.ilike(f"%{log_source.strip()}%"))
        if url and url.strip():
            query = query.filter(CallbackApiLog.url.ilike(f"%{url.strip()}%"))
        if response_status is not None:
            query = query.filter(CallbackApiLog.response_status == response_status)
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(CallbackApiLog.timestamp >= start_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid start_date format. Use YYYY-MM-DD.", {})
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                query = query.filter(CallbackApiLog.timestamp <= end_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid end_date format. Use YYYY-MM-DD.", {})

        # === Summary ===
        summary_data = query.with_entities(
            func.count().label("total_logs"),
            func.sum(case((CallbackApiLog.response_status < 400, 1), else_=0)).label("success_logs"),
            func.sum(case((CallbackApiLog.response_status >= 400, 1), else_=0)).label("failed_logs")
        ).first()

        # === Sort ===
        sort_column = valid_sort_columns[sort_by]
        query = query.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

        # === Paginate ===
        paginated_data = custom_paginate(request, query, ota_db)

        response = {
            "summary": {
                "total_count": summary_data.total_logs,
                "success_count": summary_data.success_logs,
                "failed_count": summary_data.failed_logs,
            },
            **paginated_data
        }

        return common_response(http_status.HTTP_200_OK, SUCCESS, response)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), "/callback-api-logs")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), "/callback-api-logs")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

@router.get("/callback-api-log/{log_id}")
async def get_callback_api_log_details(
    log_id: int = Path(...),
    ota_db: Session = Depends(get_ota_db_session),
):
    try:
        log = ota_db.query(CallbackApiLog).filter(CallbackApiLog.id == log_id).first()
        if not log:
            return common_response(http_status.HTTP_404_NOT_FOUND, DATA_NOT_FOUND, {})

        response = {
            "id": log.id,
            "timestamp": log.timestamp,
            "source": log.source,
            "log_source": log.log_source,
            "url": log.url,
            "request_body": log.request_body,
            "response_status": log.response_status,
            "response_message": log.response_message,
            "additional_info": log.additional_info,
        }

        return common_response(http_status.HTTP_200_OK, SUCCESS, response)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), f"/callback-api-log/{log_id}")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), f"/callback-api-log/{log_id}")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

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
    try:
        # permission_check = await require_permission(request, "view_api_logs")
        # if permission_check:
        #     return permission_check

        valid_sort_columns = {
            "id": SearchRequest.id,
            "created_at": SearchRequest.created_at,
            "supplier": SearchRequest.supplier,
            "origin": SearchRequest.origin,
            "destination": SearchRequest.destination,
            "status": SearchRequest.status,
            "result_count": SearchRequest.result_count
        }

        sort_by = sort_by.strip() if sort_by and sort_by.strip() else "created_at"
        sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else "desc"

        if sort_by not in valid_sort_columns:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_by field", {})
        if sort_order not in ["asc", "desc"]:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_order value", {})

        # === Base Query ===
        query = ota_db.query(
            SearchRequest.id,
            SearchRequest.search_id,
            SearchRequest.user_id,
            SearchRequest.supplier,
            SearchRequest.trip_type,
            SearchRequest.origin,
            SearchRequest.destination,
            SearchRequest.departure_date,
            SearchRequest.return_date,
            SearchRequest.currency,
            SearchRequest.result_count,
            SearchRequest.status,
            SearchRequest.created_at
        )

        # === Filters ===
        if supplier and supplier.strip():
            query = query.filter(SearchRequest.supplier.ilike(f"%{supplier.strip()}%"))
        if origin and origin.strip():
            query = query.filter(SearchRequest.origin == origin.strip().upper())
        if destination and destination.strip():
            query = query.filter(SearchRequest.destination == destination.strip().upper())
        if user_id and user_id.strip():
            query = query.filter(SearchRequest.user_id == user_id.strip())
        if status and status.strip():
            query = query.filter(SearchRequest.status == status.strip().lower())

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(SearchRequest.created_at >= start_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid start_date format. Use YYYY-MM-DD.", {})
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                query = query.filter(SearchRequest.created_at <= end_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid end_date format. Use YYYY-MM-DD.", {})

        # === Summary Aggregates ===
        summary_data = query.with_entities(
            func.count().label("total_logs"),
            func.sum(case((SearchRequest.status == 'success', 1), else_=0)).label("success_logs"),
            func.sum(case((SearchRequest.status == 'error', 1), else_=0)).label("failed_logs"),
            func.avg(SearchRequest.result_count).label("avg_results")
        ).first()

        # === Sorting ===
        sort_column = valid_sort_columns[sort_by]
        query = query.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

        # === Pagination ===
        paginated_data = custom_paginate(request, query, ota_db)

        # === Final Response ===
        response = {
            "summary": {
                "total_count": summary_data.total_logs or 0,
                "success_count": int(summary_data.success_logs or 0),
                "failed_count": int(summary_data.failed_logs or 0),
                "avg_results_per_search": round(float(summary_data.avg_results or 0), 2),
            },
            **paginated_data
        }

        return common_response(http_status.HTTP_200_OK, SUCCESS, response)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), "/flight-search-logs")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), "/flight-search-logs")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

@router.get("/flight-search-log/{search_id}")
async def get_flight_search_log_details(
    search_id: str = Path(..., description="The search_id (UUID) or internal ID"),
    ota_db: Session = Depends(get_ota_db_session),
):
    try:
        # Try finding by search_id (UUID string)
        log = ota_db.query(SearchRequest).filter(SearchRequest.search_id == search_id).first()
        
        # If not found and search_id is an integer, try finding by internal id
        if not log and search_id.isdigit():
            log = ota_db.query(SearchRequest).filter(SearchRequest.id == int(search_id)).first()

        if not log:
            return common_response(http_status.HTTP_404_NOT_FOUND, DATA_NOT_FOUND, {})

        response = {
            "id": log.id,
            "search_id": log.search_id,
            "user_id": log.user_id,
            "session_id": log.session_id,
            "supplier": log.supplier,
            "trip_type": log.trip_type,
            "cabin_class": log.cabin_class,
            "adults": log.adults,
            "children": log.children,
            "infants": log.infants,
            "origin": log.origin,
            "destination": log.destination,
            "departure_date": log.departure_date,
            "return_date": log.return_date,
            "currency": log.currency,
            "result_count": log.result_count,
            "request_metadata": log.request_metadata,
            "status": log.status,
            "created_at": log.created_at,
        }

        return common_response(http_status.HTTP_200_OK, SUCCESS, response)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), f"/flight-search-log/{search_id}")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), f"/flight-search-log/{search_id}")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

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
    try:
        # permission_check = await require_permission(request, "view_dashboard_analytics")
        # if permission_check:
        #     return permission_check

        valid_sort_columns = {
            "id": Booking.id,
            "created_at": Booking.created_at,
            "booking_reference": Booking.booking_reference,
            "total_amount": Booking.total_amount,
            "booking_status": Booking.booking_status
        }

        sort_by = sort_by.strip() if sort_by and sort_by.strip() else "created_at"
        sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else "desc"

        if sort_by not in valid_sort_columns:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_by field", {})
        if sort_order not in ["asc", "desc"]:
            return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid sort_order value", {})

        # === Base Query ===
        query = ota_db.query(Booking)

        # === Filters ===
        if pnr and pnr.strip():
            query = query.filter(Booking.pnr.ilike(f"%{pnr.strip()}%"))
        if user_id and user_id.strip():
            query = query.filter(Booking.user_id == user_id.strip())
        if booking_status and booking_status.strip():
            query = query.filter(Booking.booking_status == booking_status.strip().upper())
        if payment_status and payment_status.strip():
            query = query.filter(Booking.payment_status == payment_status.strip().upper())

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Booking.created_at >= start_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid start_date format. Use YYYY-MM-DD.", {})
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                query = query.filter(Booking.created_at <= end_dt)
            except ValueError:
                return common_response(http_status.HTTP_400_BAD_REQUEST, "Invalid end_date format. Use YYYY-MM-DD.", {})

        # === Sorting ===
        sort_column = valid_sort_columns[sort_by]
        query = query.order_by(asc(sort_column) if sort_order == "asc" else desc(sort_column))

        # === Pagination ===
        paginated_data = custom_paginate(request, query, ota_db)

        return common_response(http_status.HTTP_200_OK, SUCCESS, paginated_data)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), "/bookings")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), "/bookings")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

@router.get("/booking/{booking_id}")
async def get_booking_details(
    booking_id: str = Path(...),
    ota_db: Session = Depends(get_ota_db_session),
):
    try:
        booking = ota_db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            # Try finding by reference or PNR if not a UUID
            booking = ota_db.query(Booking).filter(
                (Booking.booking_reference == booking_id) | 
                (Booking.pnr == booking_id)
            ).first()

        if not booking:
            return common_response(http_status.HTTP_404_NOT_FOUND, DATA_NOT_FOUND, {})

        # Build detailed response
        response = {
            "booking_info": {
                "id": booking.id,
                "reference": booking.booking_reference,
                "pnr": booking.pnr,
                "status": booking.booking_status,
                "payment_status": booking.payment_status,
                "total_amount": float(booking.total_amount),
                "currency": booking.currency,
                "created_at": booking.created_at,
            },
            "segments": [
                {
                    "airline": s.airline_code,
                    "flight_number": s.flight_number,
                    "origin": s.origin,
                    "destination": s.destination,
                    "departure": s.departure_datetime,
                    "arrival": s.arrival_datetime,
                    "cabin": s.cabin_class,
                } for s in booking.segments
            ],
            "passengers": [
                {
                    "type": p.passenger_type,
                    "name": f"{p.first_name} {p.last_name}",
                    "gender": p.gender,
                    "dob": p.date_of_birth,
                    "passport": p.passport_number,
                } for p in booking.passengers
            ],
            "tickets": [
                {
                    "number": t.ticket_number,
                    "status": t.ticket_status,
                    "carrier": t.validating_carrier,
                    "issue_date": t.issue_date,
                } for t in booking.tickets
            ]
        }

        return common_response(http_status.HTTP_200_OK, SUCCESS, response)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), f"/booking/{booking_id}")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), f"/booking/{booking_id}")
        return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()