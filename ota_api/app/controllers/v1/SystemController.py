import os
import shutil
import psutil
import socket
import time
import ssl
from fastapi import FastAPI, APIRouter
import psycopg2
import redis
from config import REDIS_HOST, REDIS_DB, REDIS_PASS, REDIS_PORT
from app.helpers.common import get_error_info, common_response

router = APIRouter()

# DATABASE_URIS = [BBTM_DB_URI]


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
    """Check the status of configured databases."""
    db_health = {}
    # for uri in DATABASE_URIS:
    #     db_name = uri.rsplit("/", 1)[-1]
    #     db_health[db_name] = {"status": "unknown", "host": uri.split("@")[-1].split("/")[0]}

    #     try:
    #         conn = psycopg2.connect(uri.replace("+psycopg2://", "://"))
    #         cur = conn.cursor()
    #         cur.execute("SELECT 1")
    #         cur.fetchone()
    #         cur.close()
    #         conn.close()
    #         db_health[db_name]["status"] = "OK"
    #     except Exception as e:
    #         db_health[db_name]["status"] = f"error: {get_error_info(e)}"

    return db_health


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
    essential_processes = ["nginx", "redis-server", "celery"]
    process_health = {}
    for process in essential_processes:
        process_health[process] = "running" if process in (p.name() for p in psutil.process_iter()) else "not running"
    return process_health


@router.get("/health")
def read_health():
    health_report = {
        "server": get_server_health(),
        "databases": check_database_health(),
        "redis": check_redis_health(),
        "network": check_network_health(),
        "processes": check_process_health(),
    }

    return common_response(200, "success", health_report)
