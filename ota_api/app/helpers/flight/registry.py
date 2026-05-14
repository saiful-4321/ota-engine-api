from typing import Any, Dict

from app.services.sabre_service import SabreFlightService
# from app.services.amadeus_service import AmadeusFlightService   # ← future

SUPPLIER_REGISTRY: Dict[str, Any] = {
    "sabre": SabreFlightService,
    # "amadeus": AmadeusFlightService,   ← future
    # "travelport": TravelportService,   ← future
}

DEFAULT_SUPPLIER = "sabre"


def resolve_supplier(supplier: str) -> Any:
    key = supplier.lower().strip()
    service_cls = SUPPLIER_REGISTRY.get(key)
    if not service_cls:
        available = ", ".join(SUPPLIER_REGISTRY.keys())
        raise ValueError(f"Unknown supplier '{supplier}'. Available: {available}")
    return service_cls()
