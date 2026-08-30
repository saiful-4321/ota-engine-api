# app.services.login_activity.py
from app.helpers.common import *
from app.models.otadb.LoginActivity import LoginActivity

def get_user_roles():
    return {
        'administrator': 'System Admin',
        'admin': 'Super Admin',
        'exec': 'Executive',
        'it': 'IT',
        'associate': 'Associate',
        'client': 'Client'
    }

def login_activity(
        user, 
        remarks, 
        device_type="Mobile", 
        currentdate=None, 
        date=format_date(datetime.now(BD_TIMEZONE), "%Y%m%d"), 
        activity=None,
        conn_number=None
):
    session = None
    try:
        session = next(get_ota_db_session())
        attempt = 1
        # user role name
        user_role = get_user_roles().get(user.users_roles, 'Unknown')

        user_activity = session.query(LoginActivity).filter(LoginActivity.username == user.username, LoginActivity.date == date).order_by(LoginActivity.id.desc()).first()
        if user_activity:
            attempt = user_activity.attempt + 1 # all type(login, logout) counts

        if not currentdate:
            currentdate = format_date(datetime.now(BD_TIMEZONE), "%d/%m/%Y-%I:%M:%S %p")

        data = {
            'date': date, 
            'login_date': currentdate, 
            'username': user.username, 
            'user_role': user_role, 
            'branch': user.branch, 
            'name': user.name, 
            'ip': user.login_ip, 
            'location': activity['location'] if activity else None, 
            'browser': activity['browser'] if activity else None, 
            'os': activity['os'] if activity else None, 
            'device': activity['device'] if activity else device_type, 
            'attempt': attempt, 
            'conn_number': conn_number if conn_number else user.total_logged_in,
            'remarks': remarks
        }
        activity = LoginActivity(**data)
        session.add(activity)
        session.commit()
    except Exception as ex:
        session.rollback()
        write_log(str(ex), "login_activity")
    finally:
        if session is not None:
            session.close()