import logging
from datetime import datetime
from enum import Enum
import requests
import json
from config import APP_NAME, APP_ENV, BROKER_NAME, ERROR_LOG_ENABLED
# ERROR_MONITORING_URL
from app.helpers.constants import BD_TIMEZONE

class LogLevel(Enum):
    ERR = "ERR"
    LOG = "LOG"
    MSG = "MSG"
    DEBUG = "DEBUG"
    INFO = "INFO"
class LogSource(Enum):
    OMS_API = "OMS API"

def log_exception(exception, source, type = 'error', broker = "UFTCL"):
    # Create a log file with the current date
    log_filename = f"log/{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d')}.log"

    # Configure the logging module
    logging.basicConfig(filename=log_filename, level=logging.INFO)

    if type == 'error':
        logging.error(f"[{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}], BROKER: {BROKER_NAME},\n    Source: {source} \n    {exception}")
    elif type == 'debug':
        logging.debug(f"[{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}], BROKER: {BROKER_NAME},\n    Source: {source} \n    {exception}")
    else:
        logging.info(f"[{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}], BROKER: {BROKER_NAME},\n    Source: {source} \n    {exception}")

    if ERROR_LOG_ENABLED:
        log_monitoring(exception=exception, source=source, type=type)
    
# Monitoring system call
def log_monitoring(exception, source, type = 'error'):
    try:
        # The data you want to send to the API endpoint
        if type == 'error':
            level = "ERR"
        elif type == 'debug':
            level = "DEBUG"
        else:
            level = "INFO"
        json_data = {
            'source': source,
            'exception': f"{exception}"
        }
        data = {
            'broker': BROKER_NAME,
            'envr': APP_ENV,
            'source': APP_NAME,
            'level': level,
            'json_data': json.dumps(json_data)
        }
        # post_url=f'{ERROR_MONITORING_URL}/add_monitoring_log'
        # response = requests.post(post_url, json=data)
        return
    except Exception as ex:
        print(f"Error monitoring: {ex}")
        logging.error(f"[{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}], Failed to write monitoring log!")
        logging.error(f"[{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}], BROKER: {BROKER_NAME},\n    Source: {source} \n    {ex}")
        return
