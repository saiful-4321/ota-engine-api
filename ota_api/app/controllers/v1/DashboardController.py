from . import *
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, extract, cast, Numeric, Date
from fastapi import APIRouter, status, Depends, Request, Query
from fastapi.security import OAuth2PasswordBearer

from app.models.otadb.User import User
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.services.customPagination import custom_paginate
from app.utils.permission_helper import require_permission

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

ALLOWED_USER_TYPES = ["admin", "super_admin"]
def is_authorized(user):
    return user and user.user_role in ALLOWED_USER_TYPES

def calculate_percentage_change(current, previous):
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 2)

@router.get('/statistics/summary')
async def get_summary_statistics(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme)
):
    try:
        permission_check = await require_permission(request, "view_dashboard_analytics")
        if permission_check:
            return permission_check

        # Date calculations
        today = datetime.utcnow()
        first_day_current_month = today.replace(day=1)
        first_day_last_month = (first_day_current_month - timedelta(days=1)).replace(day=1)
        last_day_last_month = first_day_current_month - timedelta(days=1)


        # Users - Total & Active
        total_users = ota_db.query(func.count(Users.id)).scalar()
        active_users = ota_db.query(func.count(Users.id)).filter(Users.status == True).scalar()
        inactive_users = ota_db.query(func.count(Users.id)).filter(Users.status == False).scalar()

        # Users - New Registrations (Monthly Comparison)
        users_last_month = ota_db.query(func.count(Users.id)).filter(
            Users.created_at >= first_day_last_month,
            Users.created_at <= last_day_last_month
        ).scalar()
        
        users_current_month = ota_db.query(func.count(Users.id)).filter(
            Users.created_at >= first_day_current_month
        ).scalar()

        # Prepare response
        data = {
            "users": {
                "total": total_users,
                "active": active_users,
                "inactive": inactive_users
            },
            "registrations": {
                "current_month": users_current_month,
                "last_month": users_last_month,
                "diff": users_current_month - users_last_month,
                "diff_percent": calculate_percentage_change(users_current_month, users_last_month)
            }
        }

        return common_response(status.HTTP_200_OK, SUCCESS, data)

    except SQLAlchemyError as e:
        write_log(get_error_info(e), '/statistics/summary')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, e)
    except Exception as ex:
        write_log(get_error_info(ex), '/statistics/summary')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()

@router.get('/statistics/historical-users')
async def get_historical_users_statistics(
    request: Request,
    duration: str = Query("1y", regex="^(1m|3m|4m|6m|1y)$"),
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme)
):
    try:
        permission_check = await require_permission(request, "view_dashboard_analytics")
        if permission_check:
            return permission_check

        today = datetime.utcnow()
        start_of_this_week = today - timedelta(days=today.weekday())  # Monday
        start_of_last_week = start_of_this_week - timedelta(days=7)
        end_of_last_week = start_of_this_week - timedelta(seconds=1)

        # Weekly User Registrations
        this_week_users = ota_db.query(func.count(Users.id)).filter(
            Users.created_at >= start_of_this_week
        ).scalar() or 0

        last_week_users = ota_db.query(func.count(Users.id)).filter(
            Users.created_at >= start_of_last_week,
            Users.created_at <= end_of_last_week
        ).scalar() or 0

        # Historical duration filter
        duration_map = {
            "1m": today - timedelta(days=30),
            "3m": today - timedelta(days=90),
            "4m": today - timedelta(days=120),
            "6m": today - timedelta(days=180),
            "1y": today - timedelta(days=365)
        }
        from_date = duration_map[duration]

        # Query: Grouped daily user registrations
        user_history = ota_db.query(
            cast(Users.created_at, Date).label("date"),
            func.count(Users.id).label("count")
        ).filter(
            Users.created_at >= from_date
        ).group_by(
            cast(Users.created_at, Date)
        ).order_by(
            cast(Users.created_at, Date)
        ).all()

        chart_data = [
            [
                int(datetime.combine(row.date, datetime.min.time(), tzinfo=timezone.utc).timestamp()) * 1000,
                int(row.count)
            ]
            for row in user_history
        ]

        data = {
            "weekly": {
                "this_week": this_week_users,
                "last_week": last_week_users,
                "diff": this_week_users - last_week_users,
                "diff_percent": calculate_percentage_change(
                    this_week_users, last_week_users
                )
            },
            "chart_data": chart_data
        }

        return common_response(status.HTTP_200_OK, "Success", data)
    except Exception as ex:
        write_log(str(ex), '/statistics/historical-users')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error", {}, ex)
    finally:
        ota_db.close()