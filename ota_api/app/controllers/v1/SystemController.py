from fastapi import APIRouter

from app.helpers.common import common_response
from app.utils.system_health import health_report

# Health probes live in app/utils/system_health.py.
router = APIRouter()


@router.get("/health")
def read_health():
    return common_response(200, "success", health_report())
