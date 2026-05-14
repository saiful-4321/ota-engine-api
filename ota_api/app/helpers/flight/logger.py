import uuid
import datetime
from typing import Optional, Dict, Any

from app.models.sabre_schemas import FlightSearchRequest
from app.models.otadb.SearchRequest import SearchRequest
from app.helpers.common import get_ota_db_session, write_log


def log_search_request(
    request: FlightSearchRequest,
    supplier: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    search_id: Optional[str] = None,
    result_count: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    status: str = "success",
) -> None:
    db = next(get_ota_db_session())
    try:
        trip_type = "ROUND_TRIP" if request.return_date else "ONE_WAY"
        entry = SearchRequest(
            search_id    = search_id or str(uuid.uuid4()),
            user_id      = user_id,
            session_id   = session_id,
            supplier     = supplier,
            trip_type    = trip_type,
            cabin_class  = (request.cabin_class or "Y").upper(),
            adults       = request.adults,
            children     = request.children,
            infants      = request.infants,
            origin       = request.origin.upper(),
            destination  = request.destination.upper(),
            departure_date = datetime.date.fromisoformat(request.departure_date),
            return_date  = (
                datetime.date.fromisoformat(request.return_date)
                if request.return_date else None
            ),
            currency     = request.currency or "BDT",
            result_count = result_count,
            request_metadata = metadata,
            status       = status,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        db.rollback()
        write_log(exc, source="flight.logger.log_search_request", type="warning")
    finally:
        db.close()
