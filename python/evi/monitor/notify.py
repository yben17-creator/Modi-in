"""Alert delivery: Telegram and/or e-mail (both optional; configured in .env)."""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

import requests

from ..config import Settings


def send(settings: Settings, subject: str, lines: list[str]) -> list[str]:
    """Returns the list of channels that succeeded."""
    sent = []
    text = subject + "\n\n" + "\n".join(lines)
    if settings.telegram_token and settings.telegram_chat:
        try:
            r = requests.post(f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
                              json={"chat_id": settings.telegram_chat, "text": text[:4000]}, timeout=20)
            if r.ok:
                sent.append("telegram")
        except requests.RequestException:
            pass
    s = settings.smtp
    if s.get("SMTP_HOST") and s.get("ALERT_EMAIL_TO"):
        try:
            msg = MIMEText(text, _charset="utf-8")
            msg["Subject"], msg["From"], msg["To"] = subject, s.get("SMTP_USER") or s["ALERT_EMAIL_TO"], s["ALERT_EMAIL_TO"]
            with smtplib.SMTP(s["SMTP_HOST"], int(s.get("SMTP_PORT") or 587), timeout=30) as smtp:
                smtp.starttls()
                if s.get("SMTP_USER"):
                    smtp.login(s["SMTP_USER"], s.get("SMTP_PASSWORD") or "")
                smtp.send_message(msg)
            sent.append("email")
        except (smtplib.SMTPException, OSError):
            pass
    return sent
