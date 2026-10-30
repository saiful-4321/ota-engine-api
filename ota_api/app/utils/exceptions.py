from functools import wraps
from fastapi import Request, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from app.helpers.common import write_log, get_error_info, common_response
from app.helpers.constants import INTERNAL_SERVER_ERROR, SUCCESS

def handle_exceptions():
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get("request") or next((a for a in args if isinstance(a, Request)), None)
            db = kwargs.get("db") or next((a for a in args if hasattr(a, 'commit') and hasattr(a, 'rollback')), None)
            try:
                return await func(*args, **kwargs) if callable(getattr(func, '__await__', None)) else func(*args, **kwargs)
            except HTTPException as ex:
                write_log(get_error_info(ex), str(request.url))
                return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
            except SQLAlchemyError as ex:
                if db:
                    db.rollback()
                write_log(get_error_info(ex), str(request.url))
                return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
            except Exception as ex:
                if db:
                    db.rollback()
                write_log(get_error_info(ex), str(request.url))
                return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, INTERNAL_SERVER_ERROR, {}, ex)
            finally:
                if db:
                    db.close()
        return wrapper
    return decorator
