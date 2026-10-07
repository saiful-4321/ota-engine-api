import time
import threading
import requests
from typing import Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.services.supplier_config_service import SupplierConfigService, SupplierConfig
from app.utils.redis_utils import redis_helper
from app.helpers.common import write_log
from app.services.supplier_token_service import SupplierTokenService


def create_http_session() -> requests.Session:
    session = requests.Session()

    retry_strategy = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "GET", "PUT", "DELETE"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


class TravelportAuthService:
    def __init__(self, config: Optional[SupplierConfig] = None):
        self.config = config or SupplierConfigService.get_supplier_config("travelport", "flight")
        self.client_id     = self.config.client_id
        self.client_secret = self.config.client_secret
        self.auth_url      = self.config.endpoints.get("auth_url", "https://oauth.travelport.com")
        self.session       = create_http_session()

    def get_access_token(self) -> Dict:
        url = self.auth_url

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        data = {
            "grant_type": "password",
            "username": self.config.username,
            "password": self.config.password,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        try:
            write_log(f"Travelport Auth Request: POST {url} | Data: {data}", source="travelport_auth", type="info")
            response = self.session.post(url, headers=headers, data=data, timeout=15)
            write_log(f"Travelport Auth Response: {response.status_code} | Body: {response.text}", source="travelport_auth", type="info")

            if response.status_code != 200:
                raise Exception(
                    f"Travelport Auth HTTP {response.status_code} | Body: {response.text}"
                )

            token_data = response.json()

            if "access_token" not in token_data:
                raise Exception(f"Invalid Travelport token response: {token_data}")

            return token_data

        except Exception as e:
            raise Exception(f"Travelport Auth Failed | {str(e)}")


class TravelportBaseService:
    _lock = threading.Lock()

    def __init__(self, config: Optional[SupplierConfig] = None):
        self.config              = config or SupplierConfigService.get_supplier_config("travelport", "flight")
        self.auth_service        = TravelportAuthService(config=self.config)
        self.base_url            = self.config.base_url
        self.supplier_id         = self.config.supplier_id
        self.supplier_code       = self.config.supplier_code
        self.integration_provider = self.config.integration_provider

        # Access Group is specifically required for Travelport API
        self.access_group        = self.config.credentials.get("access_group", "")
        self.token_expiry_days   = self.config.token_expiry_days
        self.session             = create_http_session()

        self._access_token: Optional[str] = None
        self._token_expiry: float          = 0.0

    @property
    def token_cache_key(self) -> str:
        return f"travelport_access_token:{self.supplier_id}:{self.access_group}"

    def _refresh_token(self):
        token_data = self.auth_service.get_access_token()

        self._access_token = token_data["access_token"]
        
        expires_in = int(token_data.get("expires_in", 86400))
        
        # Save to DB
        SupplierTokenService.save_token_to_db(
            supplier_id=self.supplier_id,
            token_key=self.token_cache_key,
            access_token=self._access_token,
            expires_in_seconds=expires_in
        )

        # Cache in Redis for up to 1 hour to reduce DB hits
        redis_ttl = min(expires_in, 3600)
        redis_helper.set_data_ttl(self.token_cache_key, self._access_token, ttl_minutes=redis_ttl // 60)

        # safety buffer 60s
        self._token_expiry = time.time() + expires_in - 60

    @property
    def access_token(self) -> str:
        now = time.time()

        if self._access_token and now < self._token_expiry:
            return self._access_token

        with self._lock:
            now = time.time()
            if self._access_token and now < self._token_expiry:
                return self._access_token

            # Try fetching from Redis
            cached_token = redis_helper.get_data(self.token_cache_key)
            if cached_token:
                self._access_token = cached_token
                self._token_expiry = time.time() + 3600 # Assume valid for another 1 hour to reduce Redis hits
                return self._access_token

            # Try fetching from DB
            db_token = SupplierTokenService.get_token_from_db(self.supplier_id, self.token_cache_key)
            if db_token:
                self._access_token = db_token
                self._token_expiry = time.time() + 3600 # Assume valid for another hour locally
                # Re-cache in Redis for 1 hour
                redis_helper.set_data_ttl(self.token_cache_key, self._access_token, ttl_minutes=60)
                return self._access_token

            self._refresh_token()
            return self._access_token

    def get_headers(self, custom_headers: dict = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Version": "11",
            "Content-Version": "11"
        }
        if self.access_group:
            headers["XAUTH_TRAVELPORT_ACCESSGROUP"] = self.access_group
        elif self.config.pcc:
            # Fallback for Flight APIs when Access Group is missing
            headers["TVP-PCC-CORE"] = f"{self.config.pcc}_1G"
            
        if custom_headers:
            headers.update(custom_headers)
            
        return headers

    def request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json: dict = None,
        custom_headers: dict = None
    ) -> dict:

        # Check if the endpoint is a full URL or needs base_url
        if endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{self.base_url}{endpoint}"

        headers = self.get_headers(custom_headers)

        try:
            log_headers = {k: ("Bearer [REDACTED]" if k == "Authorization" else v) for k, v in headers.items()}
            write_log(
                f"Travelport Request: {method.upper()} {url} | Headers: {log_headers} | Params: {params} | JSON: {json}",
                source="travelport_service", type="info"
            )
            response = self.session.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=json,
                timeout=25
            )

            # If token expired → refresh once
            if response.status_code == 401:
                with self._lock:
                    self._refresh_token()

                headers = self.get_headers(custom_headers)
                log_retry_headers = {k: ("Bearer [REDACTED]" if k == "Authorization" else v) for k, v in headers.items()}
                write_log(
                    f"Travelport Request (Retry): {method.upper()} {url} | Headers: {log_retry_headers} | Params: {params} | JSON: {json}",
                    source="travelport_service", type="info"
                )
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=25
                )

            write_log(
                f"Travelport Response: {response.status_code} | Body: {response.text}",
                source="travelport_service", type="info"
            )

            # Check for HTTP errors or GDS business logic errors (often returned as 200 OK)
            err_detail = ""
            try:
                if response.text:
                    res_json = response.json()
                    
                    # Travelport wraps responses in different root keys (e.g., ReservationResponse, OfferListResponse).
                    # Search for Result.Error anywhere near the top level.
                    errors = res_json.get("Result", {}).get("Error") or []
                    if not errors:
                        for key, value in res_json.items():
                            if isinstance(value, dict) and "Result" in value:
                                errors = value.get("Result", {}).get("Error") or []
                                break
                    
                    if errors:
                        err_msgs = [f"[{e.get('category')} #{e.get('SourceCode')}] {e.get('Message')}" for e in errors if isinstance(e, dict)]
                        if err_msgs:
                            err_detail = " | " + " ; ".join(err_msgs)
            except Exception:
                pass

            if response.status_code >= 400 or err_detail:
                raise Exception(
                    f"Travelport API Error {response.status_code}{err_detail} | {response.text}"
                )

            res_data = response.json() if response.text else {}
            if isinstance(res_data, dict):
                res_data["_headers"] = dict(response.headers)
            return res_data

        except Exception as e:
            if "Travelport API Call Failed" in str(e):
                raise
            raise Exception(f"Travelport API Call Failed | {method} {url} | {str(e)}")
