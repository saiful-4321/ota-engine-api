from . import *
from fastapi import APIRouter
from app.utils.redis_utils import redis_helper
router = APIRouter()

@router.get('/clear-cache')
def clear_cache(key: str):
    return redis_helper.delete_key(key=key)
