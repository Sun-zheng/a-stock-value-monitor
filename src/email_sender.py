from __future__ import annotations

import smtplib
from email.message import EmailMessage


def send_email(settings, subject: str, body: str) -> tuple[bool, str]:
    required = [
        settings.email_from,
        settings.smtp_host,
        settings.smtp_username,
        settings.smtp_password,
    ]
    if not all(required):
        return False, "SMTP 配置不完整"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.email_from
    message["To"] = settings.email_to
    message.set_content(body)
    try:
        smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            if not settings.smtp_use_ssl:
                server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return True, "发送成功"
    except Exception as exc:
        return False, f"发送失败: {type(exc).__name__}: {exc}"
