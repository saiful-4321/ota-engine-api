from enum import Enum

class PaymentTypeEnum(str, Enum):
    CASH = "Cash"
    CHEQUE = "CHQ"
    IFT = "IFT"
    BEFTN = "BEFTN"
    RTGS = "RTGS"
    NPSB = "NPSB"
    MFS = "MFS"
    GOLD = "GOLD"
    SANCHAYAPATRA = "Sanchayapatra"

class AlertTypeEnum(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    APP = "app"
    NOTIFICATION = "notification"

class UserDevices(str, Enum):
    MOBILE = "Mobile"
    DESKTOP = "Desktop"

class UserRoleEnum(Enum):
    ADMINISTRATOR = 'admin'
    BANK = 'bank'
    MFS = 'mfs'

class FileType(str, Enum):
    pdf = "pdf"
    excel = "xlsx"

class AllowedDeviceType(str, Enum):
    ANR = "ANR"
    IPH = "IPH"
    IPD = "IPD"