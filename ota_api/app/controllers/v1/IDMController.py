from . import *
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, func
from fastapi import APIRouter, status as http_status, Depends, Request, Query
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from app.helpers.common import (
    write_log,
    get_ota_db_session,
    get_error_info,
    common_response
)
from app.services.customPagination import custom_paginate
import os
from config import BASE_DIR
from app.helpers.constants import INTERNAL_SERVER_ERROR, DATA_NOT_FOUND
from app.models.otadb.ExportDownloadManager import ExportDownloadManager
from app.utils.permission_helper import require_permission

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
    try:
        permission_check = await require_permission(request, "view_idm")
        if permission_check:
            return permission_check
        
        user = request.state.user
        user_id = user.user_id
        user_role = user.user_role

        valid_sort_columns = {
            "status": ExportDownloadManager.status,
            "created_at": ExportDownloadManager.created_at,
            "updated_at": ExportDownloadManager.updated_at,
        }

        if sort_by not in valid_sort_columns:
            return common_response(
                http_status.HTTP_400_BAD_REQUEST,
                "Invalid sort_by field",
                {}
            )

        if sort_order.lower() not in ["asc", "desc"]:
            return common_response(
                http_status.HTTP_400_BAD_REQUEST,
                "Invalid sort_order value",
                {}
            )

        query = ota_db.query(
            ExportDownloadManager.title,
            ExportDownloadManager.file_name,
            ExportDownloadManager.status,
            ExportDownloadManager.remarks,
            ExportDownloadManager.type,
            ExportDownloadManager.created_at,
            ExportDownloadManager.updated_at,
        )

        if user_role != "admin":
            query = query.filter(ExportDownloadManager.user_id == user_id)

        # filters
        if title:
            query = query.filter(ExportDownloadManager.title.ilike(f"%{title}%"))
        if created_at:
            query = query.filter(
                func.date(ExportDownloadManager.created_at) == created_at
            )
        if updated_at:
            query = query.filter(
                func.date(ExportDownloadManager.updated_at) == updated_at
            )

        # sorting
        sort_column = valid_sort_columns[sort_by]
        query = query.order_by(
            asc(sort_column) if sort_order == "asc" else desc(sort_column)
        )

        # Pagination
        paginated_data = custom_paginate(request, query, ota_db)

        # Format records
        files_list = [
            {
                "title": r.title,
                "file_name": r.file_name,
                "status": r.status,
                "remarks": r.remarks,
                "type": r.type,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
                "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else None,
            }
            for r in paginated_data["items"]
        ]
        limit = int(request.query_params.get("limit"))

        response = {
            "files": files_list,
            "total_count": paginated_data.get("total_count", 0),
            "page": paginated_data.get("current_page", 1),
            "limit": limit,
        }

        return common_response(
            http_status.HTTP_200_OK,
            "Exported files fetched successfully.",
            response
        )

    except Exception as ex:
        ota_db.rollback()
        write_log("Error@idm_list", get_error_info(ex))
        return common_response(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            INTERNAL_SERVER_ERROR,
            {},
            str(ex)
        )
    finally:
        ota_db.close()

@router.get("/{file_name}")
async def download_export_file(
    file_name: str,
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    token: str = Depends(oauth2_scheme),
):
    try:
        record = (
            ota_db.query(ExportDownloadManager)
            .filter(ExportDownloadManager.file_name == file_name)
            .first()
        )

        if not record or not record.url:
            return common_response(
                http_status.HTTP_404_NOT_FOUND,
                DATA_NOT_FOUND,
                {},
                "File record not found"
            )

        file_path = os.path.join(BASE_DIR, record.url)
        if not os.path.isfile(file_path):
            return common_response(
                http_status.HTTP_404_NOT_FOUND,
                DATA_NOT_FOUND,
                {},
                "File not found on server"
            )

        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    except Exception as ex:
        ota_db.rollback()
        write_log("Error@download_export_file", get_error_info(ex))
        return common_response(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            INTERNAL_SERVER_ERROR,
            {},
            str(ex)
        )
    finally:
        ota_db.close()

