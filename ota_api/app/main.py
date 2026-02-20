# app.main.py
import os
import re
from . import *
from pydantic import ValidationError
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, status
from slowapi.errors import RateLimitExceeded
from fastapi.exceptions import RequestValidationError
from app.middleware.AuthMiddleware import AuthMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.middleware.LogRequestMiddleware import log_request_middleware
from app.middleware.APILogMiddleware import APILogMiddleware
from fastapi.middleware.cors import CORSMiddleware
from config import ALLOWED_CORS, APP_NAME, APP_ENV
import logging

if APP_ENV == "PROD":
    app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None)
elif APP_ENV == "STG":
    app = FastAPI(title=APP_NAME, docs_url='/swg-docs', redoc_url='/swg-redocs')
else:
    app = FastAPI(title=APP_NAME)


# Define the paths to skip authentication, if route have "auth" auto spiped in middleware
auth_skip_paths = ["/", "/docs", "/redoc", "/openapi.json", "/swg-docs", "/swg-redocs", "/system/health"]
apilog_skip_paths = ["/", "/docs", "/redoc", "/openapi.json", "/swg-docs", "/swg-redocs"]

app.add_middleware(APILogMiddleware, skip_paths=apilog_skip_paths)
app.middleware("http")(log_request_middleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
app.add_middleware(AuthMiddleware, skip_paths=auth_skip_paths)
app.add_middleware(
    CORSMiddleware,
    # allow_origins=ALLOWED_CORS,  # 👈 your frontend origin
    allow_origins=["*"],  # 👈 your frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

versions = ["v1"]
for version in versions:
    controllers = get_controllers(version)
    if "AuthController" in controllers:
        app.include_router(controllers["AuthController"].router, prefix=f"/api/{version}/auth", tags=[f"Auth {version.upper()}"])
    if "DashboardController" in controllers:
        app.include_router(controllers["DashboardController"].router, prefix=f"/api/{version}/dashboard", tags=[f"User {version.upper()}"])
    if "UserController" in controllers:
        app.include_router(controllers["UserController"].router, prefix=f"/api/{version}/users", tags=[f"User {version.upper()}"])
    if "IpWhitelistController" in controllers:
        app.include_router(controllers["IpWhitelistController"].router, prefix=f"/api/{version}/ip", tags=[f"IP Manager {version.upper()}"])
    if "PermissionController" in controllers:
        app.include_router(controllers["PermissionController"].router, prefix=f"/api/{version}/permission", tags=[f"Permission Manager {version.upper()}"])
    if "SystemController" in controllers:
        app.include_router(controllers["SystemController"].router, prefix=f"/api/{version}/system", tags=[f"System {version.upper()}"])
    if "PublicController" in controllers:
        app.include_router(controllers["PublicController"].router, prefix=f"/api/{version}/public", tags=[f"Public {version.upper()}"])
    if "ReportController" in controllers:
        app.include_router(controllers["ReportController"].router, prefix=f"/api/{version}/reports", tags=[f"Reports {version.upper()}"])
    if "ExportController" in controllers:
        app.include_router(controllers["ExportController"].router, prefix=f"/api/{version}/export", tags=[f"Export {version.upper()}"])
    if "IDMController" in controllers:
        app.include_router(controllers["IDMController"].router, prefix=f"/api/{version}/idm", tags=[f"Import {version.upper()}"])    

# Processing job start
# @app.on_event("startup")
# def startup_event():
#     """Ensure the scheduler starts on app startup"""
#     if not scheduler.running:
#         logging.info("🚀 Starting Scheduler from main.py...")
#         scheduler.start()

# @app.on_event("shutdown")
# def shutdown():
#     """Shutdown the background scheduler when FastAPI stops"""
#     stop_scheduler()
# # processing job end

# Validation error exception handling
@app.exception_handler(ValidationError)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: Exception):
    errors = {}
    if isinstance(exc, (ValidationError, RequestValidationError)):
        for error in exc.errors():
            field = error["loc"][-1]  # Get only the field name (last element)
            message = error["msg"]
            errors.setdefault(field, []).append(message)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"status": status.HTTP_422_UNPROCESSABLE_ENTITY,"message": "Validation failed", "errors": errors, "data": None},
    )

# 🔹 Global Exception Handler for Rate Limiting Errors (SlowAPI)
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    match = re.search(r"([0-9]+) per ([0-9]+)", str(exc.detail))
    if match:
        limit_count, time_window = match.groups()
        error_message = f"You cannot make more than {limit_count} request(s) per {time_window} second(s)."
    else:
        error_message = "Rate limit exceeded. Please try again later."

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "status": status.HTTP_429_TOO_MANY_REQUESTS,
            "message": "Rate limit exceeded",
            "errors": {
                "limit": [error_message]
            },
            "data": None
        },
    )

# Define the root URL route
@app.get("/", response_class=HTMLResponse)
def home():
    return """
        <html>
            <head>
                <title>OTA API</title>
            </head>
            <body>
                <style> 
                    body {
                        background: linear-gradient(-45deg, #05b804, black, #272740, #23d5ab);
                        background-size: 400% 400%;
                        animation: gradient 15s ease infinite;
                        height: 98vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        flex-direction: column;
                        color: white
                    }

                    @keyframes gradient {
                        0% {
                            background-position: 0% 50%;
                        }
                        50% {
                            background-position: 100% 50%;
                        }
                        100% {
                            background-position: 0% 50%;
                        }
                    }

                </style>
                <div>
                    <div style="text-align: center">
                        <img src="https://quantfintech.ai/wp-content/uploads/2023/10/Quant-Fintech-Logo-White-300-400x266-1.png">
                        <h1 style="font-size: 4em; font-family: system-ui">Welcome to OTA API</h1>
                    </div>
                </div>
                </div>
            </body>
        </html>
    """