from . import *
from app.models.schemas import UserQueryParams
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import uuid
from fastapi import APIRouter, status as http_status, Depends, BackgroundTasks, Request
from fastapi.security import OAuth2PasswordBearer
from app.helpers.common import (
    write_log,
    get_ota_db_session,
    generate_user_file,
    get_error_info,
    common_response,
    create_export_record
)
from app.helpers.constants import INTERNAL_SERVER_ERROR, COULD_NOT_CREATE
from app.models.otadb.User import User

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
    try:
        user = request.state.user
        user_id = user.user_id
        # filename
        if filters.from_date or filters.to_date:
            if filters.from_date and filters.to_date:
                raw_title = f"user_report_{filters.from_date}_{filters.to_date}"
            elif filters.from_date:
                raw_title = f"user_report_{filters.from_date}_{datetime.now().date()}"
            else:
                raw_title = f"user_report_{datetime.now().date()}_{filters.to_date}"
        else:
            raw_title = f"user_report_{datetime.now().date()}_{datetime.now().date()}"
        # title for file
        clean_title = raw_title.replace(
            "user_report_", "User Report("
        ).replace("_", " to ") + ")"

        new_record = create_export_record(
            db=ota_db,
            user_id=user_id,
            title=f"{clean_title}.{filters.file_type.lower()}",  
            file_name="", 
            url="",
            remarks=None,
            status="pending",
            type_="Download"
        )

        if not new_record:
            return common_response(
                http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                INTERNAL_SERVER_ERROR,
                {},
                COULD_NOT_CREATE
            )

        query = ota_db.query(
            Users.name,
            Users.username,
            Users.email,
            Users.mobile,
            Users.status,
            Users.created_at
        )

        if filters.user_id:
             try:
                # Validate UUID format
                valid_uuid = uuid.UUID(filters.user_id)
                query = query.filter(Users.user_id == valid_uuid)
             except ValueError:
                # If invalid UUID, maybe return empty or ignore
                pass
        
        if filters.username:
            query = query.filter(Users.username.ilike(f"%{filters.username}%"))
        if filters.email:
            query = query.filter(Users.email.ilike(f"%{filters.email}%"))
        if filters.phone:
            query = query.filter(Users.mobile.ilike(f"%{filters.phone}%"))
        if filters.status:
            # Assuming status is stored as string 'active'/'inactive' or boolean? 
            # Model says boolean. Converting 'active' -> True, 'inactive' -> False
            if filters.status.lower() == 'active':
                query = query.filter(Users.status == True)
            elif filters.status.lower() == 'inactive':
                query = query.filter(Users.status == False)


        if filters.from_date and filters.to_date:
            query = query.filter(
                Users.created_at >= filters.from_date,
                Users.created_at < filters.to_date + timedelta(days=1)
            )
        elif filters.from_date:
            query = query.filter(Users.created_at >= filters.from_date)
        elif filters.to_date:
            query = query.filter(Users.created_at < filters.to_date + timedelta(days=1))

        query = query.order_by(Users.created_at.desc())

        user_data = query.all()

        if not user_data:
            return common_response(
                http_status.HTTP_404_NOT_FOUND,
                "No users found for the given filters.",
                {}
            )

        background_tasks.add_task(
            generate_user_file,
            new_record.id,
            user_data,
            filters.file_type,
            clean_title  
        )

        return common_response(
            http_status.HTTP_200_OK,
            "Export started successfully. Check IDM for status.",
            {"title": clean_title}
        )

    except Exception as ex:
        if 'new_record' in locals() and new_record:
            new_record.status = "failed"
            new_record.remarks = "Internal server error during export initiation"
            if not new_record.title:
                new_record.title = clean_title
            ota_db.commit()
        ota_db.rollback()
        write_log("Error@export_file", get_error_info(ex))
        return common_response(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            INTERNAL_SERVER_ERROR,
            {},
            str(ex)
        )
    finally:
        ota_db.close()