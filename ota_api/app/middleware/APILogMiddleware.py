import time
import json
import asyncio
import re
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import parse_qsl
from typing import Dict, Optional
from datetime import datetime
from app.helpers.common import save_log, get_error_info
from app.helpers.constants import BD_TIMEZONE

class APILogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, skip_paths: Optional[set] = None):
        super().__init__(app)
        self.skip_paths = skip_paths or set()

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in self.skip_paths:
            return await call_next(request)

        start_time = time.time()
        timestamp = datetime.now(BD_TIMEZONE)
        method = request.method
        url = str(request.url)
        client_ip = request.client.host if request.client else "Unknown"
        headers = dict(request.headers)
        query_params = dict(request.query_params)
        user_agent = headers.get("user-agent", "Unknown")
        content_type = headers.get("content-type", "").lower() 
        request_body, raw_body = await self.get_request_body(request, content_type)
        masked_request_body = self.mask_sensitive_data(request_body)
        raw_body_str = raw_body.decode("utf-8", errors="ignore") if raw_body else ""
        masked_raw_body = self.mask_sensitive_raw_body(raw_body_str)
        
        
        # sensitive_keys = ["username", "password", "email", "phone", "credential", "login", "auth"]
        # if any(key in masked_raw_body.lower() for key in sensitive_keys):
        #     with open("log_errors.txt", "a") as f:
        #         f.write(f"[{time.ctime()}] Sensitive data unmasked in raw_request_body: {masked_raw_body[:500]}\n")
        #         f.write(f"Original raw_body: {raw_body_str[:500]}\n")

        try:
            response = await call_next(request)
            response_status = response.status_code
            current_user = getattr(request.state, "user", None)
            username = getattr(current_user, "username", None)
            if hasattr(response, "body_iterator"):
                response_body_chunks = []
                async for chunk in response.body_iterator:
                    response_body_chunks.append(chunk)
                response_body = b"".join(response_body_chunks)
                response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=response.headers,
                    media_type=response.media_type
                )
            else:
                response_body = b""

            log_data = {
                "timestamp": timestamp,
                "method": method,
                "url": url,
                "client_ip": client_ip,
                "headers": json.dumps(headers, default=str),
                "query_params": json.dumps(query_params, default=str),
                "request_body": json.dumps(masked_request_body, default=str),
                "raw_request_body": masked_raw_body,
                "content_type": content_type,
                "user_agent": user_agent,
                "response_status": response_status,
                "response_size": len(response_body),
                "response_body": (
                    response_body.decode("utf-8", errors="ignore")
                    if response.headers.get("content-type", "").startswith("text") or
                    "application/json" in response.headers.get("content-type", "")
                    else "<binary>"
                ),
                "process_time": time.time() - start_time,
                "username": username,
            }
            asyncio.create_task(self.async_save_log(log_data))
            return response
        except Exception as e:
            error_info = get_error_info(e)
            log_data = {
                "timestamp": timestamp,
                "method": method,
                "url": url,
                "client_ip": client_ip,
                "headers": json.dumps(headers, default=str),
                "query_params": json.dumps(query_params, default=str),
                "request_body": json.dumps(masked_request_body, default=str),
                "raw_request_body": masked_raw_body,
                "content_type": content_type,
                "user_agent": user_agent,
                "response_status": 500,
                "response_size": 0,
                "response_body": "Internal Server Error",
                "process_time": time.time() - start_time,
                "error_message": str(e),
                "error_details": error_info,
                "username": username,
            }
            asyncio.create_task(self.async_save_log(log_data))
            raise

    async def get_request_body(self, request: Request, content_type: str) -> tuple[Dict, bytes]:
        raw_body = await request.body()
        async def receive():
            return {"type": "http.request", "body": raw_body, "more_body": False}
        request._receive = receive

        if not raw_body:
            return {"message": "Empty request body"}, raw_body

        if "multipart/form-data" in content_type:
            return await self.parse_multipart_body(raw_body, content_type), raw_body

        try:
            body_str = raw_body.decode("utf-8", errors="ignore")
            if body_str.startswith(("{", "[")):
                return json.loads(body_str), raw_body
            if "application/x-www-form-urlencoded" in content_type:
                return dict(parse_qsl(body_str)), raw_body
            return {"raw_body": body_str}, raw_body
        except Exception as e:
            return {"error": f"Invalid request body: {str(e)}"}, raw_body

    async def parse_multipart_body(self, body_bytes: bytes, content_type: str) -> Dict:
        try:
            if not body_bytes:
                return {"error": "Empty multipart request body"}
            match = re.search(r'boundary=(?:"([^"]+)"|([^;\s]+))', content_type, re.IGNORECASE)
            if not match:
                return {"error": f"Missing or invalid boundary in content-type: {content_type}"}
            boundary = (match.group(1) or match.group(2)).strip()
            if not boundary:
                return {"error": f"Empty boundary in content-type: {content_type}"}

            body_str = body_bytes.decode("utf-8", errors="ignore")
            boundary = f"--{boundary}"
            parts = body_str.split(boundary)
            parsed_data = {}
            for part in parts[1:-1]:
                part = part.strip()
                if not part:
                    continue
                header_end = part.find("\r\n\r\n")
                if header_end == -1:
                    continue
                headers = part[:header_end]
                content = part[header_end + 4:].strip()
                name_match = re.search(r'name="([^"]+)"', headers, re.IGNORECASE)
                if name_match:
                    name = name_match.group(1)
                    parsed_data[name] = content
            return parsed_data or {"error": "Empty multipart data"}
        except Exception as e:
            return {
                "error": f"Invalid multipart body: {str(e)}",
                "content_type": content_type,
                "raw_body_length": len(body_bytes)
            }

    def mask_sensitive_raw_body(self, raw_body: str) -> str:
        sensitive_keys = {
            "user", "password", "pass", "secret", "api_key", "token",
            "phone", "credential", "login", "auth"
        }
        if not raw_body:
            return "No raw request body"
        masked_body = raw_body
        for key in sensitive_keys:
            pattern = rf'(?is)Content-Disposition:\s*form-data;\s*name\s*=\s*"?\s*{key}\s*"?;?\s*\r\n\r\n(.*?)(?=\r\n--|$)'
            masked_body = re.sub(pattern, f'Content-Disposition: form-data; name="{key}"\r\n\r\n****', masked_body)
            pattern_url = rf'(?i){key}=[^&]+'
            masked_body = re.sub(pattern_url, f'{key}=****', masked_body)
            json_pattern = rf'(?i)"{key}"\s*:\s*"([^"]*?)"'
            masked_body = re.sub(json_pattern, f'"{key}": "****"', masked_body)
        return masked_body

    def mask_sensitive_data(self, data: any) -> any:
        sensitive_keys = {
            "user", "password", "pass", "secret", "api_key", "token",
            "phone", "credential", "login", "auth"
        }
        if isinstance(data, dict):
            return {
                k: "****" if k.lower() in sensitive_keys else self.mask_sensitive_data(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self.mask_sensitive_data(item) for item in data]
        return data

    async def async_save_log(self, log_data: Dict):
        try:
            await asyncio.get_event_loop().run_in_executor(None, save_log, log_data)
        except Exception as e:
            error_msg = f"[{time.ctime()}] Failed to save log: {str(e)}\n{json.dumps(log_data, default=str)}"
            print(error_msg)
            with open("log_errors.txt", "a") as f:
                f.write(error_msg + "\n")