from . import *
from app.helpers.common import *
from sqlalchemy import func
from sqlalchemy.sql import select
from starlette.requests import Request
from config import DEFAULT_PAGINATION
import math

def custom_paginate(request: Request, query, db, res_key = 'items'):
    try:       
        current_page = int(request.query_params["page"]) if "page" in request.query_params else 1
        per_page = int(request.query_params.get("per_page", request.query_params.get("limit", DEFAULT_PAGINATION)))
        
        # Determine if we are dealing with a SQLAlchemy Query object or a core Select object
        if hasattr(query, 'count'):
            # ORM Query object
            total_count = query.count()
            data = query.offset((current_page - 1) * per_page).limit(per_page).all()
        else:
            # Core Select object or fallback
            total_count_query = select([func.count()]).select_from(query.alias('sub'))
            total_count = db.execute(total_count_query).scalar()
            data = db.execute(query.offset((current_page - 1) * per_page).limit(per_page)).all()
            
            # Flatten rows if they contain single entities
            if data and len(data[0]) == 1:
                data = [row[0] for row in data]

        last_page = math.ceil(total_count / per_page) if per_page > 0 else 0

        paginate_data = {
            res_key: data,
            'total_count': total_count,
            'current_page': current_page,
            'last_page': last_page,
            'previous_page': request.url.include_query_params(page=current_page - 1)._url if current_page > 1 else None,
            'next_page': request.url.include_query_params(page=current_page + 1)._url if current_page < last_page else None
        }
        return paginate_data
    except Exception as ex:
        write_log(ex, 'app.services.customPagination.py')
        return {res_key: [], 'total_count': 0, 'current_page': 1, 'last_page': 0}