import pytz
from datetime import datetime , timedelta
def get_current_date_time(hours_to_add=0, timezone='Asia/Dhaka'):
    bdtimezone = pytz.timezone(timezone)
    now = datetime.now(bdtimezone)

    if hours_to_add != 0:
        now += timedelta(hours=hours_to_add)

    year = now.year
    month = str(now.month).zfill(2)
    day = str(now.day).zfill(2)
    hours = str(now.hour).zfill(2)
    minutes = str(now.minute).zfill(2)
    seconds = str(now.second).zfill(2)
    milliseconds = str(now.microsecond // 1000).zfill(3)
    formatted_date_time = f"{year}{month}{day}-{hours}:{minutes}:{seconds}.{milliseconds}"
    
    return formatted_date_time