from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.engine.url import URL
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

OTA_DB_URI = URL.create(
    drivername="mysql+pymysql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
)

ota_engine = create_engine(OTA_DB_URI, pool_pre_ping=True,  pool_size=1000, max_overflow=100, pool_recycle=500)
OtaDbSession = sessionmaker(autocommit=False, autoflush=False, bind=ota_engine)
OtaDbBase: DeclarativeMeta = declarative_base()

