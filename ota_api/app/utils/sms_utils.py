import requests
from fastapi import FastAPI, HTTPException
from config import BROKER_NAME, SMS_USERNAME, SMS_APICODE, SMS_CLI, SMS_PASSWORD, SMS_URL
from app.helpers.common import write_log
import re

app = FastAPI()

def msisdn_11(msisdn: str, include_country_code: bool = False):
    cleaned_msisdn = re.sub(r'\D', '', msisdn)
    cleaned_no = cleaned_msisdn[-11:]
    if include_country_code:
        return f"+88{cleaned_no}"
    return cleaned_no

def send_sms(data):
    match BROKER_NAME:
        case "UFTCL":
            send_sms_via_gp(data=data)
        case "ROYAL":
            send_sms_royal(data=data)
        case "CAL":
            send_cal_sms(data=data)

def send_sms_via_gp(data):
    url = SMS_URL
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "username": SMS_USERNAME,
        "password": SMS_PASSWORD,
        "apicode": SMS_APICODE,
        "msisdn": data['phone'],
        "countrycode": "880",
        "messagetype": "1",
        "message": data['message'],
        "messageid": None,
        "cli": SMS_CLI,
        "nonmasking": "1"
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        write_log(response.text, "Failed to send sms on:"+ data['phone'])
    return response.json()

def send_sms_royal(data):
    response = requests.get(f"{SMS_URL}?apikey={SMS_APICODE}&mobile={data['phone']}&text={data['message']}")
    if response.status_code != 200:
        write_log(response.text, "Failed to send sms on:" + data['phone'])
    return response.json()

def send_cal_sms(data):
    mobile_no = msisdn_11(data['phone'], True)
    response = requests.get(f"{SMS_URL}?ApiKey={SMS_APICODE}&ClientId={SMS_CLI}&SenderId={SMS_USERNAME}&MobileNumbers={mobile_no}&Message={data['message']}")
    if response.status_code != 200:
        write_log(response.text, "Failed to send sms on:" + data['phone'])
    return response.json()