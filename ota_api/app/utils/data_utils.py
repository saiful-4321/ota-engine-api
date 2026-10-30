"""
app/utils/data_utils.py

Small data-shape helpers: rows to dicts, dicts to attribute objects, Decimal-aware JSON.
"""

import json
from decimal import Decimal


def row_to_dict(row):
    return {column: getattr(row, column) for column in row.keys()}

# making a dictionary into an instance
class DictionaryToInstance:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)
