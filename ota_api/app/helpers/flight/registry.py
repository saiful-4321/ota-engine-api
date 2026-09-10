"""
app/helpers/flight/registry.py

Supplier registry mapping `integration_provider` → service class.

Resolution flow:
  1. `resolve_supplier(supplier_code, service)`:
       - Takes the unique `suppliers.code` DB key (e.g. 'SABRE-BD-DAC').
       - Loads its SupplierConfig from DB/cache (credentials, PCC, endpoints, etc.).
       - Finds the matching service class via `integration_provider` (e.g. 'sabre' → SabreFlightService).
       - Instantiates the service class with the SupplierConfig.

  2. `get_active_flight_suppliers(service)`:
       - Queries all active supplier instances for a service from DB.
       - Returns dict of { supplier_code: service_instance } for all active suppliers.
       - Use this to fan-out search to all active suppliers simultaneously.
"""

from typing import Any, Dict, List

from app.services.sabre_service import SabreFlightService
from app.services.supplier_config_service import SupplierConfigService, SupplierConfig
# from app.services.amadeus_service import AmadeusFlightService    # ← future
from app.services.travelport_service import TravelportFlightService

# Maps `integration_provider` value → service class
INTEGRATION_REGISTRY: Dict[str, Any] = {
    "sabre":      SabreFlightService,
    # "amadeus":    AmadeusFlightService,
    "travelport": TravelportFlightService,
    # "flyhub":     FlyhubFlightService,
}

# Default supplier key to use when no supplier is specified
DEFAULT_SUPPLIER = "sabre"


def resolve_supplier(supplier_code: str = DEFAULT_SUPPLIER, service: str = "flight") -> Any:
    """
    Resolve and instantiate a supplier service by either:
      - integration_provider: 'sabre', 'amadeus', etc. (resolves active supplier from DB)
      - supplier_code: 'SABRE-BD-DAC', 'AMA-BD-DAC', etc. (resolves specific supplier instance)

    Args:
        supplier_code: The integration_provider (e.g. 'sabre') or unique DB code (e.g. 'SABRE-BD-DAC').
        service:       Service name ('flight', 'hotel', etc.)

    Returns:
        An instantiated supplier service object (e.g. SabreFlightService)
        pre-loaded with credentials and config from the database.

    Raises:
        ValueError: If the supplier's integration_provider has no registered service class.
    """
    # Load dynamic config from DB/cache (resolves by code or provider)
    supplier_config: SupplierConfig = SupplierConfigService.get_supplier_config(
        supplier_code=supplier_code,
        service=service
    )

    # Map integration_provider → service class
    provider = supplier_config.integration_provider or str(supplier_code or "").lower().split("-")[0]
    service_cls = INTEGRATION_REGISTRY.get(provider)

    if not service_cls:
        supported = ", ".join(INTEGRATION_REGISTRY.keys())
        raise ValueError(
            f"No service implementation for integration_provider='{provider}' "
            f"(supplier='{supplier_code}'). Supported providers: {supported}. "
            f"Is the service class registered in INTEGRATION_REGISTRY?"
        )

    return service_cls(config=supplier_config)



def get_active_flight_suppliers(service: str = "flight") -> Dict[str, Any]:
    """
    Load ALL active supplier instances for a service and return instantiated service objects.

    Suppliers are considered active if:
      - `suppliers.is_active = 1` AND `suppliers.status = 'Active'`
      - AND the matching `supplier_service_links.status = 1` for the given service

    Returns:
        Dict mapping supplier_code → service instance.
        e.g. {'SABRE-BD-DAC': SabreFlightService(...), 'SABRE-SYL-XYZ': SabreFlightService(...)}

    Inactive suppliers or those with unregistered integration_providers are silently skipped
    with a warning log.
    """
    active_configs: List[SupplierConfig] = SupplierConfigService.get_active_suppliers(service=service)

    result: Dict[str, Any] = {}
    for cfg in active_configs:
        service_cls = INTEGRATION_REGISTRY.get(cfg.integration_provider)
        if not service_cls:
            import logging
            logging.getLogger(__name__).warning(
                f"Skipping supplier '{cfg.supplier_code}': "
                f"integration_provider='{cfg.integration_provider}' has no registered service class."
            )
            continue
        result[cfg.supplier_code] = service_cls(config=cfg)

    return result
