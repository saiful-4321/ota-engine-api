# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Application settings
APP_NAME = os.environ.get("APP_NAME", 'OTA API')  # Name of the application
APP_ENV = os.environ.get("APP_ENV", 'UAT')  # Environment type (e.g., UAT, Stg, Prod)

# Error Logging & Monitoring
ERROR_LOG_ENABLED = os.environ.get("ERROR_LOG_ENABLED", 1)
ERROR_MONITORING_URL = os.environ.get("ERROR_MONITORING_URL", 'https://monitoring.quantbd.com')  # Monitoring service URL

# MQTT Configuration (Message Queue Telemetry Transport)
MQTT_HOST = os.environ.get("MQTT_HOST", '192.168.155.22')  # MQTT broker host
MQTT_PORT = int(os.environ.get("MQTT_PORT", 7760))  # MQTT broker port
MQTT_KEEPALIVE = int(os.environ.get("MQTT_KEEPALIVE", 5))  # MQTT keepalive interval in seconds
APP_ENV_MQTT = os.environ.get("APP_ENV_MQTT", "Local")  # MQTT environment
MQTT_USER = os.environ.get("MQTT_USER", "")  # MQTT username (if required)
MQTT_PASS = os.environ.get("MQTT_PASS", "")  # MQTT password (if required)

# General App Settings
BROKER_NAME = os.environ.get("BROKER_NAME", "UFTCL")  # Broker name
DEFAULT_PAGINATION = int(os.environ.get("DEFAULT_PAGINATION", 10))  # Default pagination size
SOFTWARE_VERSION = os.environ.get("SOFTWARE_VERSION", "v1.0.0")  # Software version

# OTP Configuration
DAILY_MAX_OTP = int(os.environ.get("DAILY_MAX_OTP", 5))  # Max OTP requests per user per day
OTP_EXPIRES_TIME = int(os.environ.get("OTP_EXPIRES_TIME", 5))  # OTP expiration time in minutes
RESEND_OTP_TIME = int(os.environ.get("RESEND_OTP_TIME", 30))  # OTP resend cooldown time in seconds

# JWT (JSON Web Token) Authentication
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key")  # Secret key for signing JWT
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")  # Algorithm used for JWT
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 30))  # JWT token expiry time in minutes

DB_HOST = os.environ.get("DB_HOST", "192.168.155.22")
DB_PORT = os.environ.get("DB_PORT", "5459")
DB_USER = os.environ.get("DB_USER", "bbtmdata")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "bbtm97531")
DB_NAME = os.environ.get("DB_NAME", "otadb")

# SMTP Mail Configuration
SMTP_SERVER = os.environ.get("SMTP_SERVER", "sandbox.smtp.mailtrap.io")  # SMTP server address
SMTP_PORT = int(os.environ.get("SMTP_PORT", 2525))  # SMTP port
SMTP_USER = os.environ.get("SMTP_USER", None)  # SMTP username
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", None)  # SMTP password
SMTP_SENDER = os.environ.get("SMTP_SENDER", "backoffice@quantbd.com")  # Default sender email
SMTP_TLS = int(os.environ.get("SMTP_TLS", 0))  # Enable/Disable TLS (1=True, 0=False)

# SMS Configuration
SMS_URL = os.environ.get("SMS_URL", None)  # SMS provider API URL
SMS_USERNAME = os.environ.get("SMS_USERNAME", None)  # SMS API username
SMS_PASSWORD = os.environ.get("SMS_PASSWORD", None)  # SMS API password
SMS_CLI = os.environ.get("SMS_CLI", None)  # SMS client ID
SMS_APICODE = os.environ.get("SMS_APICODE", None)  # SMS API code

# Feature Toggles
IS_SMS_ENABLED = int(os.environ.get("IS_SMS_ENABLED", 0))  # Enable SMS notifications
IS_EMAIL_ENABLED = int(os.environ.get("IS_EMAIL_ENABLED", 1))  # Enable email notifications
IS_CRED_SMS_ENABLED = int(os.environ.get("IS_CRED_SMS_ENABLED", 0))  # Enable credit SMS
IS_CRED_EMAIL_ENABLED = int(os.environ.get("IS_CRED_EMAIL_ENABLED", 1))  # Enable credit email

# Redis Configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "192.168.155.22")  # Redis server host
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6456))  # Redis port

REDIS_PASS = os.environ.get("REDIS_PASS", "devpassword")  # Redis password
REDIS_DB = int(os.environ.get("REDIS_DB", 1))  # Redis database index

#Alliase Configuration
ACCESS_TOKEN_ALIAS = os.environ.get("ACCESS_TOKEN_ALIAS", "accessToken:")

REFRESH_TOKEN_EXPIRE_MINUTES = int(os.environ.get("REFRESH_TOKEN_EXPIRE_MINUTES", 20))
BASIC_AUTH_TOKEN = os.environ.get("BASIC_AUTH_TOKEN", "1OBfkob2kR6i6iECMRWmSO0ejX5CH1QOEpIesP0shg6cwfZ8scoqpizqPPSbSQTb")
REDIS_AUTH_WEB_DB = int(os.environ.get("REDIS_AUTH_WEB_DB", 2))


# File upload location
BASE_DIR = "/app"
UPLOAD_DIR = "exports"
ALLOWED_CORS = os.environ.get("ALLOWED_CORS", "*").split(",")
SECRET_2FA = os.environ.get("SECRET_2FA", "secretkey")
IS_SELF_SIGNUP_ENABLED=os.environ.get("IS_SELF_SIGNUP_ENABLED", 0)