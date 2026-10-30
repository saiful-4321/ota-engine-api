from fastapi import APIRouter, BackgroundTasks, Depends, Form, Header, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.helpers import authentication
from app.helpers.common import get_ota_db_session
from app.models.enums import UserDevices
from app.models.schemas import ForgotPasswordRequest, ResetForgetPasswordRequest, Verify2FAOtpRequest, VerifyOtpRequest

# Workflows live in app/helpers/authentication.py.
router = APIRouter()


@router.post("/app-version")
async def app_version(otadb: Session = Depends(get_ota_db_session)):
    return authentication.get_app_version(otadb)


@router.post("/login")
async def login(
    request: Request,
    background_tasks: BackgroundTasks,
    login_data: OAuth2PasswordRequestForm = Depends(),
    device: str = Form(UserDevices.MOBILE.value, max_length=150),
    device_id: str = Form(None, max_length=150),
    os: str = Form(None, max_length=30),
    browser: str = Form(None, max_length=100),
    location: str = Form(None, max_length=300),
    fcm_token: str = Form(None, max_length=300),
    otadb: Session = Depends(get_ota_db_session)
):
    activity = authentication.build_login_activity(request, device, device_id, os, browser, location)
    return await authentication.login(request, background_tasks, otadb, login_data.username, login_data.password, activity, fcm_token)


@router.post("/verify-2fa-otp")
async def verify_two_factor_otp(
    request: Request,
    input: Verify2FAOtpRequest,
    background_tasks: BackgroundTasks,
    otadb: Session = Depends(get_ota_db_session)
):
    return await authentication.verify_two_factor_otp(request, input, background_tasks, otadb)


@router.post("/remove-session")
async def remove_session(
    login_data: OAuth2PasswordRequestForm = Depends(),
    device: str = Form("Mobile", max_length=150),
    otadb: Session = Depends(get_ota_db_session)
):
    return authentication.remove_session(otadb, login_data.username, login_data.password, device)


@router.post("/refresh-token")
async def refresh_access_token(
    refresh_token: str = Header(None, alias="refresh-token"),
    device: str = Form("Mobile", max_length=150),
    device_id: str = Form(None, max_length=150),
    otadb: Session = Depends(get_ota_db_session)
):
    return await authentication.refresh_access_token(otadb, refresh_token, device, device_id)


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, background_tasks: BackgroundTasks, otadb: Session = Depends(get_ota_db_session)):
    return authentication.forgot_password(request, background_tasks, otadb)


@router.post("/resend-otp")
async def resend_otp(request: ForgotPasswordRequest, background_tasks: BackgroundTasks, otadb: Session = Depends(get_ota_db_session)):
    return authentication.resend_otp(request, background_tasks, otadb)


@router.post("/verify-otp")
async def verify_otp(request: VerifyOtpRequest, otadb: Session = Depends(get_ota_db_session)):
    return authentication.verify_otp(request, otadb)


@router.post("/reset-forgot-password")
async def reset_forgot_password(request: ResetForgetPasswordRequest, otadb: Session = Depends(get_ota_db_session)):
    return await authentication.reset_forgot_password(request, otadb)
