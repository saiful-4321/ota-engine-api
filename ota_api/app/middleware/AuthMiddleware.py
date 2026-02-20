from fastapi import HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.helpers.authentication import token_validation, validate_sync_token
from app.helpers.common import common_response, DictionaryToInstance
from app.models.otadb.IPWhitelist import IPWhitelist
from app.helpers.common import get_ota_db_session
from sqlalchemy.sql import func
from sqlalchemy import select
import logging
from typing import List, Optional, Any
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UNAUTHENTICATED = "Unauthenticated"
INVALID_TOKEN = "Invalid token"

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, skip_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
        self.skip_paths = skip_paths or ["/auth/login"]
        self.skip_keywords = ("auth", "public", "system")

    @contextmanager
    def _get_db_session(self):
        db_gen = get_ota_db_session()
        db = next(db_gen)
        try:
            yield db
        finally:
            db.close()

    async def dispatch(self, request: Request, call_next):
        """
        Main entry point for the middleware.
        """
        request_path = request.url.path

        # Skip authentication for specific paths or keywords
        if any(keyword in request_path for keyword in self.skip_keywords) or request_path in self.skip_paths:
            return await call_next(request)
            
        user = await self._get_authenticated_user(request)
        if isinstance(user, JSONResponse):
            return user

        request.state.user = DictionaryToInstance(**user)

        # IP Whitelist check for PSP
        if getattr(request.state.user, "entity_type", "").lower() == "psp":
            whitelist_response = await self._check_ip_whitelist(request)
            if whitelist_response is not None:
                return whitelist_response

        return await call_next(request)

    async def _get_authenticated_user(self, request: Request) -> Any:
        """
        Extract and validate the user from the request token.
        Returns user dict or JSONResponse on error.
        """
        try:
            token = await self.oauth2_scheme(request)
        except HTTPException as exc:
            if exc.status_code == 401 and "Bearer" in exc.headers.get("WWW-Authenticate", ""):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=common_response(status.HTTP_401_UNAUTHORIZED, UNAUTHENTICATED),
                    headers={"WWW-Authenticate": "Bearer"}
                )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=common_response(status.HTTP_401_UNAUTHORIZED, UNAUTHENTICATED)
            )

        token_type = request.headers.get("tokentype")
        user = await validate_sync_token(token) if token_type == "sync-token" else await token_validation(token)

        if not user:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=common_response(status.HTTP_401_UNAUTHORIZED, INVALID_TOKEN)
            )

        if not isinstance(user, dict):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=common_response(status.HTTP_401_UNAUTHORIZED, "Invalid user data format")
            )

        return user

    async def _check_ip_whitelist(self, request: Request) -> Optional[JSONResponse]:
        """
        Checks if the client IP is whitelisted for PSP users.
        Returns JSONResponse if not whitelisted or error, else None.
        """
        client_ip = request.client.host if request.client else None
        entity_id = getattr(request.state.user, "entity_id", None)

        if not client_ip:
            logger.warning("Unable to determine client IP address")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=common_response(status.HTTP_403_FORBIDDEN, "Unable to determine client IP address")
            )

        if not entity_id:
            logger.warning("Missing entity_id in user data")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=common_response(status.HTTP_401_UNAUTHORIZED, "Missing entity_id in user data")
            )

        try:
            with self._get_db_session() as db:
                query = select(IPWhitelist).where(
                    IPWhitelist.ip_address == client_ip,
                    func.lower(IPWhitelist.entity_type) == "psp",
                    IPWhitelist.entity_id == entity_id,
                    IPWhitelist.is_active == True
                )
                result = db.execute(query)
                whitelist_entry = result.first()

                if not whitelist_entry:
                    logger.warning(f"IP {client_ip} not whitelisted for PSP entity_id {entity_id}")
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content=common_response(status.HTTP_403_FORBIDDEN, f"IP {client_ip} not whitelisted")
                    )
        except Exception as e:
            logger.error(f"Database error during IP whitelist check: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=common_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error during IP validation")
            )
        return None