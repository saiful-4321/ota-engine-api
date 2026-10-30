"""
app/utils/system_health.py

Health probes for the /system/health endpoint: server metrics, Redis, network and processes.
"""

import shutil
import socket
import time

import psutil
import redis

from app.helpers.common import get_error_info
from config import REDIS_DB, REDIS_HOST, REDIS_PASS, REDIS_PORT

ESSENTIAL_PROCESSES = ["nginx", "redis-server", "celery"]


def get_server_health():
    """Retrieve system health metrics."""
    return {
        "cpu_usage": f"{psutil.cpu_percent()}%",
        "memory_usage": f"{psutil.virtual_memory().percent}%",
        "disk_usage": f"{shutil.disk_usage('/').used / shutil.disk_usage('/').total * 100:.2f}%",
        "uptime": f"{time.time() - psutil.boot_time():.2f} seconds",
        "hostname": socket.gethostname(),
        "ip_address": socket.gethostbyname(socket.gethostname()),
        "load_avg": f"{psutil.getloadavg()[0]:.2f}, {psutil.getloadavg()[1]:.2f}, {psutil.getloadavg()[2]:.2f}",  # 1, 5, 15 minutes load average
    }


def check_database_health():
    """Check the status of configured databases (no database probes are configured)."""
    return {}


def check_redis_health():
    """Check Redis health status."""
    redis_health = {"status": "unknown", "host": f"{REDIS_HOST}:{REDIS_PORT}"}
    try:
        redis_client = redis.StrictRedis(
            host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS, db=REDIS_DB
        )
        redis_client.ping()
        redis_health["status"] = "OK"
    except Exception as e:
        redis_health["status"] = f"error: {get_error_info(e)}"

    return redis_health


def check_network_health():
    """Check basic network connectivity."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return {"internet": "OK"}
    except OSError:
        return {"internet": "error: No connection"}


def check_process_health():
    """Check if essential processes are running."""
    running = {p.name() for p in psutil.process_iter()}
    return {process: "running" if process in running else "not running" for process in ESSENTIAL_PROCESSES}


def health_report():
    return {
        "server": get_server_health(),
        "databases": check_database_health(),
        "redis": check_redis_health(),
        "network": check_network_health(),
        "processes": check_process_health(),
    }
