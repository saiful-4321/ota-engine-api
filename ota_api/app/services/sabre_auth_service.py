import base64
import time
import threading
import requests
from typing import Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    SABRE_CLIENT_ID,
    SABRE_CLIENT_SECRET,
    SABRE_AUTH_SECRET,   
    SABRE_URL,
    SABRE_USERNAME,
    SABRE_PASSWORD,
    SABRE_TOKEN_EXPIRY_DAYS
)
from app.utils.redis_utils import redis_helper
from app.services.sabre_endpoints import SabreEndpoints



def create_http_session() -> requests.Session:
    session = requests.Session()

    retry_strategy = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "GET"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# =========================
# SABRE AUTH SERVICE
# =========================

class SabreAuthService:
    def __init__(self):
        self.client_id = str(SABRE_CLIENT_ID).strip()
        self.client_secret = str(SABRE_CLIENT_SECRET).strip()
        self.auth_secret = str(SABRE_AUTH_SECRET).strip() if SABRE_AUTH_SECRET else None
        self.base_url = SABRE_URL.rstrip("/")
        self.username = str(SABRE_USERNAME).strip()
        self.password = str(SABRE_PASSWORD).strip()
        self.session = create_http_session()

    def _get_encoded_credentials(self) -> str:
        # If precomputed secret exists
        if self.auth_secret:
            secret = self.auth_secret.strip()
            if secret.lower().startswith("basic "):
                secret = secret[6:].strip()

            secret = secret.replace("\n", "").replace("\r", "")
            return secret

        # Compute manually
        cid = self.client_id.strip().replace("\n", "").replace("\r", "")
        csec = self.client_secret.strip().replace("\n", "").replace("\r", "")

        raw = f"{cid}:{csec}"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")

        return encoded

    def get_access_token(self) -> Dict:
        url = f"{self.base_url}{SabreEndpoints.REST_AUTH_TOKEN}"

        headers = {
            "Authorization": f"Basic {self._get_encoded_credentials()}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        data = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password
        }

        try:
            response = self.session.post(url, headers=headers, data=data, timeout=15)

            if response.status_code != 200:
                raise Exception(
                    f"Sabre Auth HTTP {response.status_code} | Body: {response.text}"
                )

            token_data = response.json()

            if "access_token" not in token_data:
                raise Exception(f"Invalid Sabre token response: {token_data}")

            return token_data

        except Exception as e:
            raise Exception(f"Sabre Auth Failed | {str(e)}")


# =========================
# SABRE BASE SERVICE
# =========================

class SabreBaseService:
    _lock = threading.Lock()

    def __init__(self):
        self.auth_service = SabreAuthService()
        self.base_url = SABRE_URL.rstrip("/")
        self.session = create_http_session()

        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _refresh_token(self):
        token_data = self.auth_service.get_access_token()

        self._access_token = token_data["access_token"]
        
        # Cache in Redis
        ttl_minutes = SABRE_TOKEN_EXPIRY_DAYS * 24 * 60
        redis_helper.set_data_ttl("sabre_access_token", self._access_token, ttl_minutes=ttl_minutes)

        expires_in = int(token_data.get("expires_in", 3600))
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
            cached_token = redis_helper.get_data("sabre_access_token")
            if cached_token:
                self._access_token = cached_token
                self._token_expiry = time.time() + 3600 # Assume valid for another 1 hour to reduce Redis hits
                return self._access_token

            self._refresh_token()
            return self._access_token

    def get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    # =========================
    # GENERIC API REQUEST
    # =========================

    def request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json: dict = None
    ) -> dict:

        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                headers=self.get_headers(),
                params=params,
                json=json,
                timeout=20
            )

            # If token expired → refresh once
            if response.status_code == 401:
                with self._lock:
                    self._refresh_token()

                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=self.get_headers(),
                    params=params,
                    json=json,
                    timeout=20
                )

            if response.status_code >= 400:
                raise Exception(
                    f"Sabre API Error {response.status_code} | {response.text}"
                )

            return response.json()

        except Exception as e:
            raise Exception(f"Sabre API Call Failed | {method} {endpoint} | {str(e)}")
