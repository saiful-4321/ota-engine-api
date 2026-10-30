"""
app/helpers/common.py

Helpers shared by every module: the response envelope, error logging and the DB session.
Generic utilities live in app/utils (formatting, data_utils, request_utils, report_files).
"""

import json
import os
import traceback
import uuid
from datetime import datetime
from typing import Any, List, Optional, Tuple

import pytz
from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.helpers.constants import BD_TIMEZONE
from app.models.otadb.APILog import APILog
from app.services.log import log_exception
from databases.database import OtaDbSession


def common_response(status: int = 200, message: str = "Success", data: dict = {}, errors: dict = None):
    return {
        "status": status,
        "message": message,
        "errors": errors,
        "data": data
    }

def write_log(excetion, source, type = 'error'):
    print(f'{source} || {type}: {excetion}')
    log_exception(excetion, source, type)

def get_error_info(exception):
    tracebacks = traceback.extract_tb(exception.__traceback__)
    filename, line_number, func_name, _ = tracebacks[-1]
    error_message = str(exception)
    return {
        "filename": filename,
        "line_number": line_number,
        "func_name": func_name,
        "error_message": error_message,
        "traceback": traceback.format_tb(exception.__traceback__)
    }

def get_ota_db_session():
    db = OtaDbSession()
    try:
        yield db
    finally:
        db.close()

def save_log(log_data: dict):
    db = next(get_ota_db_session())
    try:
        log_entry = APILog(
            timestamp=log_data.get("timestamp"),
            method=log_data.get("method"),
            url=log_data.get("url"),
            client_ip=log_data.get("client_ip"),
            headers=log_data.get("headers"),
            query_params=log_data.get("query_params"),
            request_body=log_data.get("request_body"),
            raw_request_body=log_data.get("raw_request_body", ""),
            user_agent=log_data.get("user_agent"),
            response_status=log_data.get("response_status"),
            response_size=log_data.get("response_size"),
            response_body=log_data.get("response_body"),
            process_time=log_data.get("process_time"),
            error_message=log_data.get("error_message"),
            error_details=log_data.get("error_details"),
            username=log_data.get("username")
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error saving log: {e}")
    finally:
        db.close()
