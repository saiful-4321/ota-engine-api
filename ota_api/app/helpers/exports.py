"""
app/helpers/exports.py

Workflows behind /export (start a background report export) and /idm (the download manager
that lists and serves the generated files).

KNOWN ISSUE: the user export reads the legacy `Users` model, which is unset (see
app/helpers/users.py): the export record is created, then marked failed — unchanged from the
original controller.
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple

from fastapi import BackgroundTasks, Request, status as http_status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.helpers.common import common_response, get_error_info, get_ota_db_session, write_log
from app.helpers.constants import BD_TIMEZONE, COULD_NOT_CREATE, DATA_NOT_FOUND, INTERNAL_SERVER_ERROR
from app.helpers.users import Users  # legacy model, unset — see KNOWN ISSUE
from app.models.otadb.ExportDownloadManager import ExportDownloadManager
from app.models.schemas import UserQueryParams
from app.services.customPagination import custom_paginate
from app.utils.permission_helper import require_permission
from app.utils.query_utils import sort_clause
from app.utils.report_files import create_report_excel, create_report_pdf
from config import BASE_DIR, UPLOAD_DIR

XLSX_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
_IDM_SORT_COLUMNS = {
    "status": ExportDownloadManager.status,
    "created_at": ExportDownloadManager.created_at,
    "updated_at": ExportDownloadManager.updated_at,
}


def _server_error(ota_db: Session, ex: Exception, source: str) -> dict:
    ota_db.rollback()
    write_log(source, get_error_info(ex))
    return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, str(ex))


def _format_datetime(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


# ── Export records & file generation ─────────────────────────────────────────

def create_export_record(
    db: Session,
    user_id: uuid.UUID,
    title: str,
    file_name: str,
    type_: str,
    url: Optional[str] = None,
    remarks: Optional[str] = None,
    status: str = "pending",
) -> Optional[ExportDownloadManager]:
    try:
        new_export = ExportDownloadManager(
            user_id=user_id,
            title=title,
            file_name=file_name,
            url=url,
            remarks=remarks,
            status=status,
            type=type_,            
            created_at = datetime.now(BD_TIMEZONE),
            updated_at=None
        )

        db.add(new_export)
        db.commit()
        db.refresh(new_export)

        return new_export

    except SQLAlchemyError as e:
        db.rollback()
        write_log(e, source="create_export_record", type="error")
        return None


def generate_user_file(record_id: int, data: List[Tuple[Any]], file_type: str, clean_title: str):
    db: Session = next(get_ota_db_session())
    record = None
    try:
        record = db.query(ExportDownloadManager).filter_by(id=record_id).first()
        if not record:
            record = db.query(ExportDownloadManager).filter_by(id=record_id).first() # Retry once
            if not record:
                write_log(f"{file_type.upper()} generation failed: Record not found", "generate_user_file_background")
                return

        record.status = "processing"
        db.commit()

        file_name = f"{clean_title}_({datetime.now(BD_TIMEZONE).strftime('%d%m%Y%H%M%S')}).{file_type}"
        record.file_name = file_name
        
        output_folder = os.path.join(BASE_DIR, UPLOAD_DIR, "users")
        os.makedirs(output_folder, exist_ok=True)

        output_path = os.path.join(output_folder, file_name)

        if not data:
            record.status = "failed"
            record.remarks = f"No data provided for {file_type.upper()} generation"
            db.commit()
            return

        # Define fields to export
        field_names = [
            "name", "username", "email", "mobile", "status", "created_at"
        ]
        headers = ["SL."] + [''.join(word.capitalize() for word in col.split('_')) for col in field_names]

        rows = []
        for idx, row_obj in enumerate(data, start=1):
            row = [idx]
            for col in field_names:
                val = getattr(row_obj, col)
                if isinstance(val, datetime):
                    val = val.strftime("%Y-%m-%d %H:%M:%S")
                row.append(val if val is not None else "")
            rows.append(row)

        table_data = [headers] + rows

        success = False
        if file_type.lower() == "pdf":
            # Reusing existing PDF generator if suitable, otherwise might need a specific one. 
            # create_report_pdf is generic enough based on previous inspection
            success = create_report_pdf(file_path=output_path, title=clean_title, data=table_data)
        elif file_type.lower() == "xlsx":
            success = create_report_excel(file_path=output_path, title=clean_title, data=table_data)
        else:
            record.status = "failed"
            record.remarks = f"Unsupported file type: {file_type}"
            db.commit()
            return

        if success:
            record.url = output_path
            record.status = "completed"
            record.remarks = None
        else:
            record.status = "failed"
            record.remarks = f"Unknown {file_type.upper()} generation error"

        db.commit()

    except Exception as e:
        if record:
            record.status = "failed"
            record.remarks = f"Exception during {file_type.upper()} processing: {str(e)}"
            db.commit()
        write_log(e, "generate_user_file_background")
    finally:
        db.close()


# ── User export ──────────────────────────────────────────────────────────────

def user_report_title(filters: UserQueryParams) -> str:
    """'User Report(2026-01-01 to 2026-10-31)' — open ends default to today."""
    today = datetime.now().date()
    return f"User Report({filters.from_date or today} to {filters.to_date or today})"


def _user_export_query(ota_db: Session, filters: UserQueryParams):
    query = ota_db.query(Users.name, Users.username, Users.email, Users.mobile, Users.status, Users.created_at)

    if filters.user_id:
        try:
            query = query.filter(Users.user_id == uuid.UUID(filters.user_id))
        except ValueError:
            pass  # not a UUID: no user_id filter
    if filters.username:
        query = query.filter(Users.username.ilike(f"%{filters.username}%"))
    if filters.email:
        query = query.filter(Users.email.ilike(f"%{filters.email}%"))
    if filters.phone:
        query = query.filter(Users.mobile.ilike(f"%{filters.phone}%"))
    if filters.status:
        if filters.status.lower() == 'active':
            query = query.filter(Users.status == True)
        elif filters.status.lower() == 'inactive':
            query = query.filter(Users.status == False)
    if filters.from_date:
        query = query.filter(Users.created_at >= filters.from_date)
    if filters.to_date:
        query = query.filter(Users.created_at < filters.to_date + timedelta(days=1))

    return query.order_by(Users.created_at.desc())


def export_users(request: Request, filters: UserQueryParams, background_tasks: BackgroundTasks, ota_db: Session) -> dict:
    new_record = None
    clean_title = user_report_title(filters)
    try:
        new_record = create_export_record(
            db=ota_db,
            user_id=request.state.user.user_id,
            title=f"{clean_title}.{filters.file_type.lower()}",
            file_name="",
            url="",
            remarks=None,
            status="pending",
            type_="Download"
        )
        if not new_record:
            return common_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, COULD_NOT_CREATE)

        user_data = _user_export_query(ota_db, filters).all()
        if not user_data:
            return common_response(http_status.HTTP_404_NOT_FOUND, "No users found for the given filters.", {})

        background_tasks.add_task(generate_user_file, new_record.id, user_data, filters.file_type, clean_title)
        return common_response(http_status.HTTP_200_OK, "Export started successfully. Check IDM for status.",
                               {"title": clean_title})
    except Exception as ex:
        if new_record:
            new_record.status = "failed"
            new_record.remarks = "Internal server error during export initiation"
            if not new_record.title:
                new_record.title = clean_title
            ota_db.commit()
        return _server_error(ota_db, ex, "Error@export_file")
    finally:
        ota_db.close()


# ── Download manager (IDM) ───────────────────────────────────────────────────

async def list_exports(request: Request, ota_db: Session, sort_by: str, sort_order: str, title: str,
                       created_at: str, updated_at: str) -> dict:
    """The caller's exported files (admins see everyone's)."""
    try:
        permission_check = await require_permission(request, "view_idm")
        if permission_check:
            return permission_check

        order, error = sort_clause(sort_by, sort_order, _IDM_SORT_COLUMNS, "created_at")
        if error:
            return common_response(http_status.HTTP_400_BAD_REQUEST, error, {})

        query = ota_db.query(
            ExportDownloadManager.title,
            ExportDownloadManager.file_name,
            ExportDownloadManager.status,
            ExportDownloadManager.remarks,
            ExportDownloadManager.type,
            ExportDownloadManager.created_at,
            ExportDownloadManager.updated_at,
        )
        user = request.state.user
        if user.user_role != "admin":
            query = query.filter(ExportDownloadManager.user_id == user.user_id)
        if title:
            query = query.filter(ExportDownloadManager.title.ilike(f"%{title}%"))
        if created_at:
            query = query.filter(func.date(ExportDownloadManager.created_at) == created_at)
        if updated_at:
            query = query.filter(func.date(ExportDownloadManager.updated_at) == updated_at)

        paginated_data = custom_paginate(request, query.order_by(order), ota_db)
        response = {
            "files": [
                {
                    "title": r.title,
                    "file_name": r.file_name,
                    "status": r.status,
                    "remarks": r.remarks,
                    "type": r.type,
                    "created_at": _format_datetime(r.created_at),
                    "updated_at": _format_datetime(r.updated_at),
                }
                for r in paginated_data["items"]
            ],
            "total_count": paginated_data.get("total_count", 0),
            "page": paginated_data.get("current_page", 1),
            "limit": int(request.query_params.get("limit")),
        }
        return common_response(http_status.HTTP_200_OK, "Exported files fetched successfully.", response)
    except Exception as ex:
        return _server_error(ota_db, ex, "Error@idm_list")
    finally:
        ota_db.close()


def download_export(file_name: str, ota_db: Session):
    """The generated file, or a 404 body when the record or the file is missing."""
    try:
        record = ota_db.query(ExportDownloadManager).filter(ExportDownloadManager.file_name == file_name).first()
        if not record or not record.url:
            return common_response(http_status.HTTP_404_NOT_FOUND, DATA_NOT_FOUND, {}, "File record not found")

        file_path = os.path.join(BASE_DIR, record.url)
        if not os.path.isfile(file_path):
            return common_response(http_status.HTTP_404_NOT_FOUND, DATA_NOT_FOUND, {}, "File not found on server")

        return FileResponse(path=file_path, filename=os.path.basename(file_path), media_type=XLSX_MEDIA_TYPE)
    except Exception as ex:
        return _server_error(ota_db, ex, "Error@download_export_file")
    finally:
        ota_db.close()
