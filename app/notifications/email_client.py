import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger("notifications.email")


async def send_email(to: str, subject: str, body_html: str) -> bool:
    try:
        if settings.email_provider == "sendgrid":
            return await _send_sendgrid(to, subject, body_html)
        return await _send_smtp(to, subject, body_html)
    except Exception as exc:
        logger.error("email.send_failed", to=to, subject=subject, error=str(exc))
        return False


async def _send_sendgrid(to: str, subject: str, body_html: str) -> bool:
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": settings.email_from},
        "subject": subject,
        "content": [{"type": "text/html", "value": body_html}],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
            timeout=10,
        )
    if resp.status_code not in (200, 202):
        logger.warning("email.sendgrid_error", status=resp.status_code, body=resp.text[:200])
        return False
    logger.info("email.sent_sendgrid", to=to, subject=subject)
    return True


async def _send_smtp(to: str, subject: str, body_html: str) -> bool:
    def _blocking_send():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.email_from
        msg["To"] = to
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.sendmail(settings.email_from, [to], msg.as_string())

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _blocking_send)
    logger.info("email.sent_smtp", to=to, subject=subject)
    return True
