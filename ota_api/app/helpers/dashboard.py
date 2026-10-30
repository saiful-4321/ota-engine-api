"""
app/helpers/dashboard.py

Workflows behind the /dashboard statistics endpoints.

KNOWN ISSUE: the statistics count the legacy `Users` model, which is unset (see
app/helpers/users.py), so both endpoints end in the 500 branch — unchanged from the original controller.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Request, status
from sqlalchemy import Date, cast, func
from sqlalchemy.orm import Session

from app.helpers.common import common_response, get_error_info, write_log
from app.helpers.constants import INTERNAL_SERVER_ERROR, SUCCESS
from app.helpers.users import Users  # legacy model, unset — see KNOWN ISSUE
from app.utils.permission_helper import require_permission

VIEW_PERMISSION = "view_dashboard_analytics"
HISTORY_DAYS = {"1m": 30, "3m": 90, "4m": 120, "6m": 180, "1y": 365}


def calculate_percentage_change(current, previous):
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 2)


def _comparison(current, previous) -> dict:
    return {"diff": current - previous, "diff_percent": calculate_percentage_change(current, previous)}


def _count_users(ota_db: Session, *criteria):
    return ota_db.query(func.count(Users.id)).filter(*criteria).scalar()


async def summary_statistics(request: Request, ota_db: Session) -> dict:
    try:
        permission_check = await require_permission(request, VIEW_PERMISSION)
        if permission_check:
            return permission_check

        today = datetime.utcnow()
        first_day_current_month = today.replace(day=1)
        last_day_last_month = first_day_current_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)

        users_current_month = _count_users(ota_db, Users.created_at >= first_day_current_month)
        users_last_month = _count_users(ota_db, Users.created_at >= first_day_last_month,
                                        Users.created_at <= last_day_last_month)
        data = {
            "users": {
                "total": _count_users(ota_db),
                "active": _count_users(ota_db, Users.status == True),
                "inactive": _count_users(ota_db, Users.status == False),
            },
            "registrations": {
                "current_month": users_current_month,
                "last_month": users_last_month,
                **_comparison(users_current_month, users_last_month),
            },
        }
        return common_response(status.HTTP_200_OK, SUCCESS, data)
    except Exception as ex:
        write_log(get_error_info(ex), '/statistics/summary')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
    finally:
        ota_db.close()


async def historical_users_statistics(request: Request, duration: str, ota_db: Session) -> dict:
    try:
        permission_check = await require_permission(request, VIEW_PERMISSION)
        if permission_check:
            return permission_check

        today = datetime.utcnow()
        start_of_this_week = today - timedelta(days=today.weekday())  # Monday
        start_of_last_week = start_of_this_week - timedelta(days=7)
        end_of_last_week = start_of_this_week - timedelta(seconds=1)

        this_week_users = _count_users(ota_db, Users.created_at >= start_of_this_week) or 0
        last_week_users = _count_users(ota_db, Users.created_at >= start_of_last_week,
                                       Users.created_at <= end_of_last_week) or 0

        # Daily registrations over the requested period, as [epoch_ms, count] chart points
        day = cast(Users.created_at, Date)
        user_history = ota_db.query(day.label("date"), func.count(Users.id).label("count")).filter(
            Users.created_at >= today - timedelta(days=HISTORY_DAYS[duration])
        ).group_by(day).order_by(day).all()
        chart_data = [
            [int(datetime.combine(row.date, datetime.min.time(), tzinfo=timezone.utc).timestamp()) * 1000, int(row.count)]
            for row in user_history
        ]

        data = {
            "weekly": {
                "this_week": this_week_users,
                "last_week": last_week_users,
                **_comparison(this_week_users, last_week_users),
            },
            "chart_data": chart_data,
        }
        return common_response(status.HTTP_200_OK, "Success", data)
    except Exception as ex:
        write_log(str(ex), '/statistics/historical-users')
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error", {}, ex)
    finally:
        ota_db.close()
