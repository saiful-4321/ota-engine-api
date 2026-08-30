from decimal import Decimal
from typing import Dict, Any, List

def calculate_mock_commission(base_fare: Decimal) -> Dict[str, Any]:
    """
    Temporary mock commission calculator.
    This will be replaced by the proper commission engine later.
    
    Returns a dict with the total commission amount and a detailed breakdown.
    """
    # E.g., 7% base commission on the base fare, and 2% override commission.
    base_commission_amount = base_fare * Decimal("0.07")
    override_commission_amount = base_fare * Decimal("0.02")
    
    total = base_commission_amount + override_commission_amount
    
    breakdown = [
        {
            "code": "BASE_COMM",
            "amount": base_commission_amount,
            "percentage": Decimal("7.0000"),
            "description": "Standard 7% Airline Commission"
        },
        {
            "code": "OVERRIDE",
            "amount": override_commission_amount,
            "percentage": Decimal("2.0000"),
            "description": "Special 2% Agent Override Commission"
        }
    ]
    
    return {
        "total": total,
        "breakdown": breakdown
    }
