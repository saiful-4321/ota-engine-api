"""
app/utils/formatting.py

Date and number formatting helpers (Bangladesh time zone, money and percentages).
"""

import math
from datetime import datetime
from decimal import Decimal, ROUND_DOWN

import pytz
from dateutil.parser import parse as dataParser

from app.helpers.constants import BD_TIMEZONE


def format_date(date, format: str = "%Y-%m-%d"):
    if date:
        try:
            if isinstance(date, str):
                parsed_date = dataParser(date, tzinfos={'Asia/Dhaka': pytz.timezone('Asia/Dhaka')})
            elif isinstance(date, datetime):
                parsed_date = date.astimezone(BD_TIMEZONE)
            else:
                parsed_date = datetime.now(BD_TIMEZONE)
            return parsed_date.strftime(format)
        except:
            return None
    return None

def format_str_to_date(date_str):
    try:
        if date_str is not None:
            return datetime.strptime(date_str, '%d%m%Y').strftime('%Y-%m-%d')
        return date_str
    except ValueError as e:
        return None

def custom_float(number):
    number_str = str(number)
    if len(number_str) >= 2:
        modified_number_str = number_str[:-2] + '.' + number_str[-2:]
        modified_number_decimal = Decimal(modified_number_str).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        return str(modified_number_decimal)
    else:
        return number_str

def formatted_float(value, default=0.00):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError, AttributeError):
        return default

def handle_float(value):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        else:
            return float(value)
    else:
        return value

def custom_round(number, decimal_places=0):
    factor = 10 ** decimal_places
    rounded = int(number * factor) / factor
    return rounded

def convert_million_to_crore(million):  
    if not isinstance(million, (float, int, Decimal)):
        return million
    return formatted_float(million / 10)
