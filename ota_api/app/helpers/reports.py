"""
app/helpers/reports.py

Workflows behind the read-only /reports endpoints: users, API logs, callback logs, flight-search
logs and bookings. List reports validate sorting and dates (400 on bad input), apply filters,
add summary aggregates where useful and paginate.

KNOWN ISSUE: the users report and user details read the legacy `Users` model, which is unset
(see app/helpers/users.py), so they end in the 500 branch — unchanged from the original controller.
"""

import uuid
from typing import Optional

from fastapi import HTTPException, Request, status as http_status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.helpers.common import common_response, get_error_info, write_log
from app.helpers.constants import DATA_NOT_FOUND, INTERNAL_SERVER_ERROR, SUCCESS
from app.helpers.users import Users  # legacy model, unset — see KNOWN ISSUE
from app.models.otadb.APILog import APILog
from app.models.otadb.AtBooking import AtBooking
from app.models.otadb.AtPricingSnapshot import AtPricingSnapshot
from app.models.otadb.CallbackApiLog import CallbackApiLog
from app.models.otadb.SearchRequest import SearchRequest
from app.services.customPagination import custom_paginate
from app.utils.permission_helper import require_permission
from app.utils.query_utils import filter_contains, filter_date_range, sort_clause

_API_LOG_SORT = {
    "id": APILog.id,
    "timestamp": APILog.timestamp,
    "method": APILog.method,
    "url": APILog.url,
    "client_ip": APILog.client_ip,
    "response_status": APILog.response_status,
    "process_time": APILog.process_time,
}
_CALLBACK_LOG_SORT = {
    "id": CallbackApiLog.id,
    "timestamp": CallbackApiLog.timestamp,
    "source": CallbackApiLog.source,
    "log_source": CallbackApiLog.log_source,
    "url": CallbackApiLog.url,
    "response_status": CallbackApiLog.response_status,
}
_SEARCH_LOG_SORT = {
    "id": SearchRequest.id,
    "created_at": SearchRequest.created_at,
    "supplier": SearchRequest.supplier,
    "origin": SearchRequest.origin,
    "destination": SearchRequest.destination,
    "status": SearchRequest.status,
    "result_count": SearchRequest.result_count,
}
_BOOKING_SORT = {
    "id": AtBooking.id,
    "created_at": AtBooking.created_at,
    "booking_reference": AtBooking.booking_reference,
    "total_amount": AtPricingSnapshot.customer_total,
    "booking_status": AtBooking.status,
}


def _bad_request(message: str) -> dict:
    return common_response(http_status.HTTP_400_BAD_REQUEST, message, {})


def _not_found() -> dict:
    return common_response(http_status.HTTP_404_NOT_FOUND, DATA_NOT_FOUND, {})


def _server_error(ex: Exception, source: str) -> dict:
    write_log(get_error_info(ex), source)
    return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)


def _ok(data) -> dict:
    return common_response(http_status.HTTP_200_OK, SUCCESS, data)


# ── Users ────────────────────────────────────────────────────────────────────

async def users_report(request: Request, ota_db: Session, filters: dict, start_date: Optional[str],
                       end_date: Optional[str], sort_by: str, sort_order: str) -> dict:
    try:
        permission_check = await require_permission(request, "view_dashboard_analytics")
        if permission_check:
            return permission_check

        sort_columns = {
            "id": Users.id,
            "user_id": Users.user_id,
            "name": Users.name,
            "username": Users.username,
            "email": Users.email,
            "mobile": Users.mobile,
            "status": Users.status,
            "created_at": Users.created_at,
        }
        order, error = sort_clause(sort_by, sort_order, sort_columns, "created_at")
        if error:
            return _bad_request(error)

        query = ota_db.query(Users)
        if filters.get("user_id"):
            try:
                query = query.filter(Users.user_id == uuid.UUID(filters["user_id"]))
            except ValueError:
                pass  # not a UUID: no user_id filter
        for field in ("name", "username", "email", "mobile"):
            query = filter_contains(query, getattr(Users, field), filters.get(field))
        user_status = (filters.get("status") or "").strip().lower()
        if user_status == 'active':
            query = query.filter(Users.status == True)
        elif user_status == 'inactive':
            query = query.filter(Users.status == False)
        query, error = filter_date_range(query, Users.created_at, start_date, end_date)
        if error:
            return _bad_request(error)

        total_count = query.with_entities(func.count()).scalar()
        data_query = query.with_entities(
            Users.id, Users.user_id, Users.name, Users.username, Users.email, Users.mobile, Users.status, Users.created_at,
        ).order_by(order)
        return _ok({"summary": {"total_count": total_count}, **custom_paginate(request, data_query, ota_db)})
    except Exception as ex:
        return _server_error(ex, '/users-list')
    finally:
        ota_db.close()


def user_details(user_id: str, ota_db: Session) -> dict:
    try:
        try:
            valid_uuid = uuid.UUID(user_id)
        except ValueError:
            return _bad_request("Invalid user_id format")

        user = ota_db.query(Users).filter(Users.user_id == valid_uuid).first()
        if not user:
            return _not_found()
        return _ok({
            "id": user.id,
            "user_id": str(user.user_id),
            "name": user.name,
            "username": user.username,
            "email": user.email,
            "mobile": user.mobile,
            "status": user.status,
            "created_at": user.created_at,
        })
    except HTTPException:
        raise
    except Exception as ex:
        return _server_error(ex, f'/user/{user_id}')
    finally:
        ota_db.close()


# ── API logs ─────────────────────────────────────────────────────────────────

async def api_logs(request: Request, ota_db: Session, filters: dict, start_date: Optional[str],
                   end_date: Optional[str], sort_by: str, sort_order: str) -> dict:
    try:
        permission_check = await require_permission(request, "view_api_logs")
        if permission_check:
            return permission_check

        order, error = sort_clause(sort_by, sort_order, _API_LOG_SORT, "timestamp")
        if error:
            return _bad_request(error)

        query = ota_db.query(
            APILog.id, APILog.timestamp, APILog.method, APILog.url, APILog.client_ip, APILog.headers,
            APILog.query_params, APILog.request_body, APILog.user_agent, APILog.response_status, APILog.response_size,
            APILog.response_body, APILog.process_time, APILog.raw_request_body, APILog.error_message,
            APILog.error_details, APILog.username,
        )
        query = filter_contains(query, APILog.method, filters.get("method"))
        query = filter_contains(query, APILog.url, filters.get("url"))
        query = filter_contains(query, APILog.client_ip, filters.get("client_ip"))
        if filters.get("status_code"):
            query = query.filter(APILog.response_status == filters["status_code"])
        query, error = filter_date_range(query, APILog.timestamp, start_date, end_date)
        if error:
            return _bad_request(error)

        summary = query.with_entities(
            func.count().label("total_logs"),
            func.sum(case((APILog.response_status < 400, 1), else_=0)).label("success_logs"),
            func.sum(case((APILog.response_status >= 400, 1), else_=0)).label("failed_logs"),
            func.coalesce(func.avg(APILog.process_time), 0).label("avg_response_time")
        ).first()
        return _ok({
            "summary": {
                "total_count": summary.total_logs,
                "success_count": summary.success_logs,
                "failed_count": summary.failed_logs,
                "avg_response_time": round(float(summary.avg_response_time), 4),
            },
            **custom_paginate(request, query.order_by(order), ota_db),
        })
    except Exception as ex:
        return _server_error(ex, "/api-logs")
    finally:
        ota_db.close()


def api_log_details(log_id: int, ota_db: Session) -> dict:
    try:
        log = ota_db.query(APILog).filter(APILog.id == log_id).first()
        if not log:
            return _not_found()
        return _ok({
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
        })
    except Exception as ex:
        return _server_error(ex, f"/api-log/{log_id}")
    finally:
        ota_db.close()


# ── Callback API logs ────────────────────────────────────────────────────────

async def callback_api_logs(request: Request, ota_db: Session, filters: dict, start_date: Optional[str],
                            end_date: Optional[str], sort_by: str, sort_order: str) -> dict:
    try:
        permission_check = await require_permission(request, "view_callback_api_logs")
        if permission_check:
            return permission_check

        order, error = sort_clause(sort_by, sort_order, _CALLBACK_LOG_SORT, "timestamp")
        if error:
            return _bad_request(error)

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
        query = filter_contains(query, CallbackApiLog.source, filters.get("source"))
        query = filter_contains(query, CallbackApiLog.log_source, filters.get("log_source"))
        query = filter_contains(query, CallbackApiLog.url, filters.get("url"))
        if filters.get("response_status") is not None:
            query = query.filter(CallbackApiLog.response_status == filters["response_status"])
        query, error = filter_date_range(query, CallbackApiLog.timestamp, start_date, end_date)
        if error:
            return _bad_request(error)

        summary = query.with_entities(
            func.count().label("total_logs"),
            func.sum(case((CallbackApiLog.response_status < 400, 1), else_=0)).label("success_logs"),
            func.sum(case((CallbackApiLog.response_status >= 400, 1), else_=0)).label("failed_logs")
        ).first()
        return _ok({
            "summary": {
                "total_count": summary.total_logs,
                "success_count": summary.success_logs,
                "failed_count": summary.failed_logs,
            },
            **custom_paginate(request, query.order_by(order), ota_db),
        })
    except Exception as ex:
        return _server_error(ex, "/callback-api-logs")
    finally:
        ota_db.close()


def callback_api_log_details(log_id: int, ota_db: Session) -> dict:
    try:
        log = ota_db.query(CallbackApiLog).filter(CallbackApiLog.id == log_id).first()
        if not log:
            return _not_found()
        return _ok({
            "id": log.id,
            "timestamp": log.timestamp,
            "source": log.source,
            "log_source": log.log_source,
            "url": log.url,
            "request_body": log.request_body,
            "response_status": log.response_status,
            "response_message": log.response_message,
            "additional_info": log.additional_info,
        })
    except Exception as ex:
        return _server_error(ex, f"/callback-api-log/{log_id}")
    finally:
        ota_db.close()


# ── Flight search logs ───────────────────────────────────────────────────────

def flight_search_logs(request: Request, ota_db: Session, filters: dict, start_date: Optional[str],
                       end_date: Optional[str], sort_by: str, sort_order: str) -> dict:
    try:
        order, error = sort_clause(sort_by, sort_order, _SEARCH_LOG_SORT, "created_at")
        if error:
            return _bad_request(error)

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
        query = filter_contains(query, SearchRequest.supplier, filters.get("supplier"))
        exact = {
            SearchRequest.origin: (filters.get("origin") or "").strip().upper(),
            SearchRequest.destination: (filters.get("destination") or "").strip().upper(),
            SearchRequest.user_id: (filters.get("user_id") or "").strip(),
            SearchRequest.status: (filters.get("status") or "").strip().lower(),
        }
        for column, value in exact.items():
            if value:
                query = query.filter(column == value)
        query, error = filter_date_range(query, SearchRequest.created_at, start_date, end_date)
        if error:
            return _bad_request(error)

        summary = query.with_entities(
            func.count().label("total_logs"),
            func.sum(case((SearchRequest.status == 'success', 1), else_=0)).label("success_logs"),
            func.sum(case((SearchRequest.status == 'error', 1), else_=0)).label("failed_logs"),
            func.avg(SearchRequest.result_count).label("avg_results")
        ).first()
        return _ok({
            "summary": {
                "total_count": summary.total_logs or 0,
                "success_count": int(summary.success_logs or 0),
                "failed_count": int(summary.failed_logs or 0),
                "avg_results_per_search": round(float(summary.avg_results or 0), 2),
            },
            **custom_paginate(request, query.order_by(order), ota_db),
        })
    except Exception as ex:
        return _server_error(ex, "/flight-search-logs")
    finally:
        ota_db.close()


def flight_search_log_details(search_id: str, ota_db: Session) -> dict:
    """Looks up by search_id (UUID), then by numeric id."""
    try:
        log = ota_db.query(SearchRequest).filter(SearchRequest.search_id == search_id).first()
        if not log and search_id.isdigit():
            log = ota_db.query(SearchRequest).filter(SearchRequest.id == int(search_id)).first()
        if not log:
            return _not_found()
        return _ok({
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
        })
    except Exception as ex:
        return _server_error(ex, f"/flight-search-log/{search_id}")
    finally:
        ota_db.close()


# ── Bookings ─────────────────────────────────────────────────────────────────

def bookings(request: Request, ota_db: Session, filters: dict, start_date: Optional[str],
             end_date: Optional[str], sort_by: str, sort_order: str) -> dict:
    try:
        order, error = sort_clause(sort_by, sort_order, _BOOKING_SORT, "created_at")
        if error:
            return _bad_request(error)

        query = ota_db.query(AtBooking).outerjoin(
            AtPricingSnapshot,
            (AtBooking.id == AtPricingSnapshot.booking_id) & (AtPricingSnapshot.is_active == True)
            & (AtPricingSnapshot.snapshot_type == 'BOOKING')
        )
        query = filter_contains(query, AtBooking.pnr, filters.get("pnr"))
        user_id = (filters.get("user_id") or "").strip()
        if user_id:
            query = query.filter(AtBooking.user_id == user_id)
        booking_status = (filters.get("booking_status") or "").strip().lower()
        if booking_status:
            query = query.filter(AtBooking.status == booking_status)
        query, error = filter_date_range(query, AtBooking.created_at, start_date, end_date)
        if error:
            return _bad_request(error)

        return _ok(custom_paginate(request, query.order_by(order), ota_db))
    except Exception as ex:
        return _server_error(ex, "/bookings")
    finally:
        ota_db.close()


def _booking_details_payload(booking) -> dict:
    active_snapshot = next((s for s in booking.pricing_snapshots if s.is_active), None)
    return {
        "booking_info": {
            "id": booking.id,
            "reference": booking.booking_reference,
            "pnr": booking.pnr,
            "status": booking.status,
            "total_amount": float(active_snapshot.customer_total) if active_snapshot else 0.0,
            "currency": active_snapshot.base_currency if active_snapshot else "BDT",
            "created_at": booking.created_at,
        },
        "segments": [
            {
                "airline": s.carrier_code,
                "flight_number": s.flight_number,
                "origin": s.origin,
                "destination": s.destination,
                "departure": s.departure_at,
                "arrival": s.arrival_at,
                "cabin": s.cabin_class,
            } for s in booking.segments
        ],
        "passengers": [
            {
                "type": p.type,
                "name": f"{p.first_name} {p.last_name}",
                "gender": p.gender,
                "dob": p.dob,
                "passport": p.passport_no,
            } for p in booking.passengers
        ],
        "tickets": [
            {
                "number": t.ticket_number,
                "status": t.status,
                "carrier": t.validating_carrier,
                "issue_date": t.issued_at,
            } for t in booking.tickets
        ],
    }


def booking_details(booking_id: str, ota_db: Session) -> dict:
    """Looks up by numeric id, then by booking reference or PNR."""
    try:
        booking = ota_db.query(AtBooking).filter(AtBooking.id == booking_id).first()
        if not booking:
            booking = ota_db.query(AtBooking).filter(
                (AtBooking.booking_reference == booking_id) | (AtBooking.pnr == booking_id)
            ).first()
        if not booking:
            return _not_found()
        return _ok(_booking_details_payload(booking))
    except Exception as ex:
        return _server_error(ex, f"/booking/{booking_id}")
    finally:
        ota_db.close()
