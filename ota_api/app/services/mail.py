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

            # Check if we should send as HTML
            user_info = getattr(self, "userInfo", None)
            button = getattr(self, "button", None)
            has_html = "<" in self.body and ">" in self.body
            is_html_email = has_html or user_info is not None or button is not None

            if is_html_email:
                user_name = "User"
                if user_info:
                    user_name = getattr(user_info, 'name', None) or getattr(user_info, 'username', 'User')

                button_html = ""
                if button:
                    btn_text = button.get("text", "")
                    btn_link = button.get("link", "#")
                    if btn_link and btn_link != "#":
                        button_html = f"""
                        <div style="margin: 30px 0; text-align: center;">
                            <a href="{btn_link}" style="background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%); color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block; box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2), 0 2px 4px -1px rgba(6, 182, 212, 0.1); transition: all 0.2s;">{btn_text}</a>
                        </div>
                        """
                    else:
                        button_html = f"""
                        <div style="margin: 30px 0; text-align: center;">
                            <div style="background-color: #f3f4f6; border: 1px solid #e5e7eb; display: inline-block; padding: 16px 32px; border-radius: 12px; box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.06);">
                                <span style="font-family: monospace; font-size: 24px; font-weight: 700; color: #1f2937; letter-spacing: 2px;">{btn_text}</span>
                            </div>
                        </div>
                        """

                email_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f9fafb; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #374151;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f9fafb; padding: 20px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05); border: 1px solid #f3f4f6;">
                    <!-- Top Gradient Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%); height: 8px;"></td>
                    </tr>
                    <!-- Main Body Content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <h2 style="margin-top: 0; margin-bottom: 20px; color: #111827; font-size: 20px; font-weight: 600;">Hello {user_name},</h2>
                            <div style="font-size: 16px; line-height: 1.6; color: #4b5563;">
                                {self.body}
                            </div>
                            {button_html}
                            <hr style="border: 0; border-top: 1px solid #f3f4f6; margin: 30px 0;">
                            <p style="font-size: 12px; color: #9ca3af; line-height: 1.5; margin: 0;">
                                This is an automated email from SkyNovia OTA. If you did not request this email, please ignore it or contact our support team.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
                message.attach(MIMEText(email_html, "html"))
            else:
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
    def __init__(self, recipient_email: str, subject: str, body: str, attachment_path: str = None, userInfo = None, button = None):
        self.recipient_email = recipient_email
        self.subject = subject
        self.body = body
        self.attachment_path = attachment_path
        self.userInfo = userInfo
        self.button = button
