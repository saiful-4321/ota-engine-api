from . import *

from app.helpers.authentication import *
from app.services.location_service import LocationService

from fastapi import APIRouter, Depends, status, Header, Request, Query


router = APIRouter()

 
@router.get("/locations")
async def search_locations(
    request: Request,
    q: str = Query(None, min_length=1, max_length=50),
    otadb: Session = Depends(get_ota_db_session),
    current_user: dict = Depends(validate_sync_token)
):
    try:
        if not current_user:
            return common_response(status.HTTP_401_UNAUTHORIZED, "Unauthorized")

        if not q:
            return common_response(status.HTTP_200_OK, "Query string required", [])

        location_service = LocationService(otadb)
        results = location_service.search_locations(q)
        return common_response(status.HTTP_200_OK, "Success", results)
    except Exception as e:
        write_log(get_error_info(e), "search_locations")
        return common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")
