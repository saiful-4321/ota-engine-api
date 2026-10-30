"""
app/utils/query_utils.py

Query-building helpers shared by the list endpoints: whitelisted sorting, date-range and
"contains" filters. Each validator returns (result, error_message) so callers can answer 400.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import asc, desc

SORT_ORDERS = ("asc", "desc")
DATE_FORMAT = "%Y-%m-%d"


def sort_clause(sort_by: Optional[str], sort_order: Optional[str], columns: Dict[str, Any],
                default_column: str) -> Tuple[Any, Optional[str]]:
    """ORDER BY clause for one of the whitelisted `columns`. Blank values fall back to the defaults."""
    sort_by = sort_by.strip() if sort_by and sort_by.strip() else default_column
    sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else "desc"
    if sort_by not in columns:
        return None, "Invalid sort_by field"
    if sort_order not in SORT_ORDERS:
        return None, "Invalid sort_order value"
    column = columns[sort_by]
    return (asc(column) if sort_order == "asc" else desc(column)), None


def filter_date_range(query: Any, column: Any, start_date: Optional[str],
                      end_date: Optional[str]) -> Tuple[Any, Optional[str]]:
    """Filters `column` to start_date <= value <= end_date (YYYY-MM-DD, either one optional)."""
    if start_date:
        try:
            query = query.filter(column >= datetime.strptime(start_date, DATE_FORMAT))
        except ValueError:
            return query, "Invalid start_date format. Use YYYY-MM-DD."
    if end_date:
        try:
            query = query.filter(column <= datetime.strptime(end_date, DATE_FORMAT))
        except ValueError:
            return query, "Invalid end_date format. Use YYYY-MM-DD."
    return query, None


def filter_contains(query: Any, column: Any, value: Optional[str]) -> Any:
    """Case-insensitive "contains" filter; blank values are ignored."""
    if value and value.strip():
        query = query.filter(column.ilike(f"%{value.strip()}%"))
    return query
