import time
import threading
import requests
from typing import Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.services.supplier_config_service import SupplierConfigService, SupplierConfig
from app.utils.redis_utils import redis_helper


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
            response = self.session.post(url, headers=headers, data=data, timeout=15)

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
        ttl_minutes = expires_in // 60
        redis_helper.set_data_ttl(self.token_cache_key, self._access_token, ttl_minutes=ttl_minutes)

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
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=25
                )

            if response.status_code >= 400:
                err_detail = ""
                try:
                    res_json = response.json()
                    errors = (
                        res_json.get("CatalogProductOfferingsResponse", {}).get("Result", {}).get("Error")
                        or res_json.get("Result", {}).get("Error")
                        or []
                    )
                    err_msgs = [f"[{e.get('category')} #{e.get('SourceCode')}] {e.get('Message')}" for e in errors]
                    if err_msgs:
                        err_detail = " | " + " ; ".join(err_msgs)
                except Exception:
                    pass

                raise Exception(
                    f"Travelport API Error {response.status_code}{err_detail} | {response.text}"
                )

            return response.json() if response.text else {}

        except Exception as e:
            if "Travelport API Call Failed" in str(e):
                raise
            raise Exception(f"Travelport API Call Failed | {method} {url} | {str(e)}")
