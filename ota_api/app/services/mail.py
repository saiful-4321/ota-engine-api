# app.services.mail.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from app.helpers.common import write_log, get_error_info
from config import SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_SENDER, SMTP_TLS

class MailMixin:
    def send_email(self):
        try:
            message = MIMEMultipart()
            message["From"] = SMTP_SENDER
            message["To"] = self.recipient_email
            message["Subject"] = self.subject
            message.attach(MIMEText(self.body, "plain"))

            if self.attachment_path:
                with open(self.attachment_path, "rb") as attachment:
                    part = MIMEApplication(attachment.read(), Name=self.attachment_path)
                    part['Content-Disposition'] = f'attachment; filename="{self.attachment_path}"'
                    message.attach(part)

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                if SMTP_TLS:
                    server.starttls()  # Secure the connection
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_SENDER, self.recipient_email, message.as_string())
        except smtplib.SMTPException as e:
            write_log(get_error_info(e), f"SMTP error occurred at app.services.mail.py")
        except Exception as e:
            write_log(get_error_info(e), f"app.services.mail.py")

class MailFunctions(MailMixin):
    def __init__(self, recipient_email: str, subject: str, body: str, attachment_path: str = None):
        self.recipient_email = recipient_email
        self.subject = subject
        self.body = body
        self.attachment_path = attachment_path
