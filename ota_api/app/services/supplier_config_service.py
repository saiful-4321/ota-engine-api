import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session
from databases.database import OtaDbSession
from app.models.otadb.Supplier import Supplier
from app.models.otadb.SupplierConfiguration import SupplierConfiguration
from app.models.otadb.SupplierServiceLink import SupplierServiceLink
from app.utils.redis_utils import redis_helper

logger = logging.getLogger(__name__)



@dataclass
class SupplierConfig:
    supplier_id: int
    supplier_uuid: str
    supplier_name: str
    supplier_code: str                          # Unique instance code e.g. 'SABRE-BD-DAC'
    integration_provider: str                   # Engine key e.g. 'sabre', 'amadeus'
    supplier_type: str = "GDS"
    service: str = "flight"
    endpoints: Dict[str, Any] = field(default_factory=dict)
    credentials: Dict[str, Any] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)
    raw_config: Dict[str, Any] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        url = (
            self.endpoints.get("base_url")
            or self.endpoints.get("flight_search")
            or self.endpoints.get("flight_api")
        )
        return str(url or "").rstrip("/")


    @property
    def client_id(self) -> str:
        return str(
            self.credentials.get("client_id")
            or self.credentials.get("api_key")
            or self.credentials.get("app_key")
            or ""
        ).strip()


    @property
    def client_secret(self) -> str:
        return str(
            self.credentials.get("client_secret")
            or self.credentials.get("api_secret")
            or self.credentials.get("app_secret")
            or ""
        ).strip()


    @property
    def auth_secret(self) -> Optional[str]:
        asec = self.credentials.get("auth_secret")
        return str(asec).strip() if asec else None


    @property
    def username(self) -> str:
        return str(
            self.credentials.get("username")
            or self.credentials.get("api_user")
            or ""
        ).strip()


    @property
    def password(self) -> str:
        return str(
            self.credentials.get("password")
            or self.credentials.get("api_pass")
            or ""
        ).strip()


    @property
    def pcc(self) -> str:
        return str(
            self.credentials.get("pcc")
            or self.credentials.get("office_id")
            or ""
        ).strip()


    @property
    def lniata(self) -> str:
        return str(
            self.credentials.get("lniata")
            or self.credentials.get("printer_id")
            or ""
        ).strip()


    @property
    def token_expiry_days(self) -> int:
        try:
            return int(self.credentials.get("token_expiry_days") or 7)
        except (ValueError, TypeError):
            return 7


    @property
    def currency(self) -> str:
        return self.settings.get("currency", "BDT")

    @property
    def station_code(self) -> str:
        return self.settings.get("station_code", "DAC")

    @property
    def country_code(self) -> str:
        return self.settings.get("country_code", "BD")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_id": self.supplier_id,
            "supplier_uuid": self.supplier_uuid,
            "supplier_name": self.supplier_name,
            "supplier_code": self.supplier_code,
            "integration_provider": self.integration_provider,
            "supplier_type": self.supplier_type,
            "service": self.service,
            "endpoints": self.endpoints,
            "credentials": self.credentials,
            "settings": self.settings,
            "raw_config": self.raw_config
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SupplierConfig":
        return cls(
            supplier_id=data.get("supplier_id", 0),
            supplier_uuid=data.get("supplier_uuid", ""),
            supplier_name=data.get("supplier_name", ""),
            supplier_code=data.get("supplier_code", ""),
            integration_provider=data.get("integration_provider", ""),
            supplier_type=data.get("supplier_type", "GDS"),
            service=data.get("service", "flight"),
            endpoints=data.get("endpoints", {}),
            credentials=data.get("credentials", {}),
            settings=data.get("settings", {}),
            raw_config=data.get("raw_config", {})
        )


class SupplierConfigService:
    CACHE_PREFIX = "supplier_config"
    ACTIVE_SUPPLIERS_CACHE_KEY = "supplier_config:active_list:{service}"
    CACHE_TTL_MINUTES = 5

    @classmethod
    def _build_config_from_row(
        cls,
        supplier: Supplier,
        config_row: Optional[SupplierConfiguration],
        link: Optional[SupplierServiceLink],
        service_key: str
    ) -> SupplierConfig:
        def _parse_json(val):
            if isinstance(val, dict):
                return val
            if val:
                try:
                    return json.loads(val)
                except Exception:
                    pass
            return {}

        endpoints = {}
        credentials = {}
        settings = {}
        raw_config = {}

        if config_row:
            endpoints    = _parse_json(config_row.api_endpoints)
            credentials  = _parse_json(config_row.api_credentials)
            settings     = _parse_json(config_row.api_settings)
            raw_config   = {
                "hold_option":        config_row.hold_option,
                "hold_time_limit":    config_row.hold_time_limit,
                "can_book":           config_row.can_book,
                "status_search_book": config_row.status_search_book,
                "default_airlines":   config_row.default_airlines,
                "city_name":          config_row.city_name,
                "state_code":         config_row.state_code,
            }

        # Apply service-link credential override (plain JSON — not Laravel-encrypted)
        if link and link.credentials_override:
            try:
                override_data = json.loads(link.credentials_override)
                if isinstance(override_data, dict):
                    credentials.update(override_data)
            except Exception:
                pass   # Silently ignore encrypted / non-JSON overrides

        return SupplierConfig(
            supplier_id=supplier.id,
            supplier_uuid=supplier.uuid,
            supplier_name=supplier.name,
            supplier_code=supplier.code,
            integration_provider=(supplier.integration_provider or "").lower().strip(),
            supplier_type=supplier.supplier_type or "GDS",
            service=service_key,
            endpoints=endpoints,
            credentials=credentials,
            settings=settings,
            raw_config=raw_config
        )

    # ── Public API ────────────────────────────────────────────────────────────

    @classmethod
    def get_supplier_config(
        cls,
        supplier_code: str = "sabre",
        service: str = "flight",
        db: Optional[Session] = None,
        use_cache: bool = True
    ) -> SupplierConfig:
        ident = str(supplier_code or "sabre").strip()
        service_key = service.lower().strip()
        cache_key = f"{cls.CACHE_PREFIX}:{ident.lower()}:{service_key}"

        # 1. Try Redis cache
        if use_cache:
            try:
                cached_json = redis_helper.get_data(cache_key)
                if cached_json:
                    data = json.loads(cached_json) if isinstance(cached_json, str) else cached_json
                    return SupplierConfig.from_dict(data)
            except Exception as e:
                logger.warning(f"Redis cache miss/error for {cache_key}: {e}")

        # 2. Query database
        should_close = db is None
        if db is None:
            db = OtaDbSession()

        try:
            # 2a. Try exact match on `code` (e.g. 'SABRE-BD-DAC')
            supplier = (
                db.query(Supplier)
                .filter(
                    Supplier.code.ilike(ident),
                    Supplier.is_active == 1
                )
                .first()
            )

            # 2b. If not found by code, match by `integration_provider` (e.g. 'sabre') with active service link
            if not supplier:
                supplier = (
                    db.query(Supplier)
                    .join(SupplierServiceLink, SupplierServiceLink.supplier_id == Supplier.id)
                    .filter(
                        Supplier.integration_provider.ilike(ident),
                        Supplier.is_active == 1,
                        Supplier.status == "Active",
                        SupplierServiceLink.service.ilike(service_key),
                        SupplierServiceLink.status == 1
                    )
                    .order_by(Supplier.id.asc())
                    .first()
                )

            # 2c. Fallback match by `integration_provider` without strict service link status
            if not supplier:
                supplier = (
                    db.query(Supplier)
                    .filter(
                        Supplier.integration_provider.ilike(ident),
                        Supplier.is_active == 1
                    )
                    .order_by(Supplier.id.asc())
                    .first()
                )

            # 2d. Fallback match by name substring (e.g. 'sabre')
            if not supplier:
                supplier = (
                    db.query(Supplier)
                    .filter(
                        Supplier.name.ilike(f"%{ident}%"),
                        Supplier.is_active == 1
                    )
                    .order_by(Supplier.id.asc())
                    .first()
                )

            if not supplier:
                logger.warning(
                    f"Supplier '{supplier_code}' not found or inactive in DB. Using fallback defaults."
                )
                return cls._create_fallback_config(supplier_code, service_key)

            link = db.query(SupplierServiceLink).filter(
                SupplierServiceLink.supplier_id == supplier.id,
                SupplierServiceLink.service.ilike(service_key)
            ).first()

            if link and link.status == 0:
                logger.warning(
                    f"Service '{service_key}' is disabled for supplier '{supplier.code}'."
                )

            config_row = db.query(SupplierConfiguration).filter(
                SupplierConfiguration.supplier_id == supplier.id
            ).first()

            config_obj = cls._build_config_from_row(supplier, config_row, link, service_key)

            # 3. Cache result under both requested identifier and actual supplier code
            if use_cache:
                try:
                    c_json = json.dumps(config_obj.to_dict())
                    redis_helper.set_data_ttl(cache_key, c_json, ttl_minutes=cls.CACHE_TTL_MINUTES)
                    if config_obj.supplier_code.lower() != ident.lower():
                        alt_key = f"{cls.CACHE_PREFIX}:{config_obj.supplier_code.lower()}:{service_key}"
                        redis_helper.set_data_ttl(alt_key, c_json, ttl_minutes=cls.CACHE_TTL_MINUTES)
                except Exception as e:
                    logger.warning(f"Failed to cache supplier config in Redis: {e}")

            return config_obj

        except Exception as e:
            logger.error(
                f"Error querying supplier config for '{supplier_code}': {e}", exc_info=True
            )
            return cls._create_fallback_config(supplier_code, service_key)
        finally:
            if should_close:
                db.close()


    @classmethod
    def get_active_suppliers(
        cls,
        service: str = "flight",
        db: Optional[Session] = None,
        use_cache: bool = True
    ) -> List[SupplierConfig]:
        service_key = service.lower().strip()
        list_cache_key = cls.ACTIVE_SUPPLIERS_CACHE_KEY.format(service=service_key)

        # 1. Try Redis cache (list of supplier codes)
        if use_cache:
            try:
                cached = redis_helper.get_data(list_cache_key)
                if cached:
                    codes = json.loads(cached) if isinstance(cached, str) else cached
                    # Resolve each code individually (they will each be cached separately)
                    configs = []
                    for code in codes:
                        try:
                            configs.append(
                                cls.get_supplier_config(code, service=service_key, use_cache=True)
                            )
                        except Exception as exc:
                            logger.warning(f"Skipping cached supplier code '{code}': {exc}")
                    if configs:
                        return configs
            except Exception as e:
                logger.warning(f"Redis active-supplier list cache miss/error: {e}")

        # 2. Query database
        should_close = db is None
        if db is None:
            db = OtaDbSession()

        try:
            # Join suppliers ↔ supplier_service_links to find all active-for-service rows
            active_links = (
                db.query(SupplierServiceLink, Supplier)
                .join(Supplier, Supplier.id == SupplierServiceLink.supplier_id)
                .filter(
                    SupplierServiceLink.service.ilike(service_key),
                    SupplierServiceLink.status == 1,
                    Supplier.is_active == 1,
                    Supplier.status == "Active"
                )
                .all()
            )

            if not active_links:
                logger.warning(f"No active suppliers found for service='{service_key}'.")
                return []

            configs = []
            active_codes = []

            for link, supplier in active_links:
                config_row = db.query(SupplierConfiguration).filter(
                    SupplierConfiguration.supplier_id == supplier.id
                ).first()

                config_obj = cls._build_config_from_row(supplier, config_row, link, service_key)
                configs.append(config_obj)
                active_codes.append(supplier.code)

                # Cache each supplier individually
                if use_cache:
                    try:
                        per_key = f"{cls.CACHE_PREFIX}:{supplier.code.upper()}:{service_key}"
                        redis_helper.set_data_ttl(
                            per_key,
                            json.dumps(config_obj.to_dict()),
                            ttl_minutes=cls.CACHE_TTL_MINUTES
                        )
                    except Exception as e:
                        logger.warning(f"Failed caching supplier '{supplier.code}': {e}")

            # Cache the active code list
            if use_cache and active_codes:
                try:
                    redis_helper.set_data_ttl(
                        list_cache_key,
                        json.dumps(active_codes),
                        ttl_minutes=cls.CACHE_TTL_MINUTES
                    )
                except Exception as e:
                    logger.warning(f"Failed caching active supplier list: {e}")

            logger.info(
                f"Loaded {len(configs)} active supplier(s) for service='{service_key}': "
                + ", ".join(f"{c.supplier_code} ({c.integration_provider})" for c in configs)
            )
            return configs

        except Exception as e:
            logger.error(f"Error fetching active suppliers for service='{service_key}': {e}", exc_info=True)
            return []
        finally:
            if should_close:
                db.close()

    @classmethod
    def _create_fallback_config(cls, supplier_code: str, service: str) -> SupplierConfig:
        logger.error(
            f"DB unavailable for supplier '{supplier_code}'. "
            f"Returning empty fallback config — supplier credentials must be configured in the database."
        )
        return SupplierConfig(
            supplier_id=0,
            supplier_uuid="",
            supplier_name=supplier_code,
            supplier_code=supplier_code,
            integration_provider=supplier_code.lower().split("-")[0],
            supplier_type="GDS",
            service=service,
            endpoints={},
            credentials={},
            settings={}
        )

