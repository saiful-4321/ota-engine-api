import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.helpers import users
from app.helpers.common import get_ota_db_session
from app.models.schemas import UserSchema

# Workflows live in app/helpers/users.py.
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@router.get('/list')
async def get_user_list(
    request: Request,
    ota_db: Session = Depends(get_ota_db_session),
    entity_type: Optional[str] = Query(None, description="Type of entity (e.g., 'PSP', 'Broker')"),
    name: str = Query(None),
    username: str = Query(None),
    email: str = Query(None),
    mobile: str = Query(None),
    user_role: str = Query(None),
    entity_id: str = Query(None),
    status: str = Query(None),
    token: str = Depends(oauth2_scheme),
):
    filters = {"name": name, "username": username, "email": email, "mobile": mobile,
               "user_role": user_role, "entity_id": entity_id, "status": status}
    return await users.list_users(request, ota_db, entity_type, filters)


@router.post("/create")
async def create_user(request: Request, input: UserSchema, ota_db: Session = Depends(get_ota_db_session)):
    return await users.create_user(request, input, ota_db)


@router.put("/update/{user_id}")
async def update_user(user_id: uuid.UUID, input: UserSchema, request: Request, ota_db: Session = Depends(get_ota_db_session)):
    return await users.update_user(request, user_id, input, ota_db)


@router.delete("/delete/{user_id}")
async def delete_user(user_id: uuid.UUID, request: Request, ota_db: Session = Depends(get_ota_db_session)):
    return await users.delete_user(request, user_id, ota_db)
