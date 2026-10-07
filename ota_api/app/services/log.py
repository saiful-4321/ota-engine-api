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
    import os
    os.makedirs("log", exist_ok=True)
    log_filename = f"log/{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d')}.log"
    
    logger = logging.getLogger("ota_file_logger")
    logger.setLevel(logging.INFO)
    
    # Avoid adding multiple handlers if already present
    if not logger.handlers:
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if type == 'error':
        logger.error(f"[{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}], BROKER: {BROKER_NAME},\n    Source: {source} \n    {exception}")
    elif type == 'debug':
        logger.debug(f"[{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}], BROKER: {BROKER_NAME},\n    Source: {source} \n    {exception}")
    else:
        logger.info(f"[{datetime.now(BD_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}], BROKER: {BROKER_NAME},\n    Source: {source} \n    {exception}")


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
