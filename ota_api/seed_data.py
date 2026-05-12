from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker
import random
from datetime import datetime
from faker import Faker
from passlib.hash import bcrypt as pwd_context
from app.models.otadb.User import User
from app.models.otadb.ActivityLog import ActivityLog
from app.models.otadb.LoginActivity import LoginActivity
from app.models.otadb.APILog import APILog
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

# Setup Database Connection
DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
session = Session()

fake = Faker()

def seed_users(n=100):
    print(f"Seeding {n} users...")
    users = []
    for _ in range(n):
        users.append({
            "username": fake.user_name(),
            "password": pwd_context.hash('12345'),
            "email": fake.email(),
            "name": fake.name(),
            "uuid": fake.uuid4(),
            "phone": fake.phone_number()[:20],
            "status": 'Active',
            "max_login": 5,
            "logged_in": 0,
            "is_tc_accepted": True,
            "is_2fa_enabled": True
        })
    session.bulk_insert_mappings(User, users)
    session.commit()
    print("Users seeded.")

def seed_activity_logs(n=200):
    print(f"Seeding {n} activity logs...")
    logs = []
    # Fetch existing usernames
    usernames = [u.username for u in session.query(User.username).limit(50).all()]
    if not usernames:
        usernames = ['admin']

    for _ in range(n):
        logs.append({
            "username": random.choice(usernames),
            "type": random.choice(['LOGIN', 'LOGOUT', 'ORDER', 'UPDATE']),
            "details": fake.sentence(),
            "platform": random.choice(['WEB', 'MOBILE']),
            "created_at": fake.date_time_this_year()
        })
    session.bulk_insert_mappings(ActivityLog, logs)
    session.commit()
    print("Activity logs seeded.")

def seed_api_logs(n=200):
    print(f"Seeding {n} API logs...")
    logs = []
    for _ in range(n):
        logs.append({
             "method": random.choice(['GET', 'POST', 'PUT', 'DELETE']),
             "url": fake.url(),
             "client_ip": fake.ipv4(),
             "response_status": random.choice([200, 201, 400, 401, 404, 500]),
             "process_time": random.uniform(0.1, 2.0),
             "username": fake.user_name()
        })
    session.bulk_insert_mappings(APILog, logs)
    session.commit()
    print("API logs seeded.")

if __name__ == "__main__":
    try:
        seed_users(100) # Adjust number as needed
        seed_activity_logs(500)
        seed_api_logs(500)
        print("Seeding complete!")
    except Exception as e:
        print(f"Error seeding data: {e}")
        session.rollback()
    finally:
        session.close()
