"""SMTP transport for confirmation mail. Tokens and credentials are never logged."""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit

from app.core.config import settings


def signup_available() -> bool:
    url = urlsplit(settings.PUBLIC_APP_URL)
    return bool(settings.PUBLIC_SIGNUP_ENABLED and settings.SMTP_HOST
        and settings.SMTP_USERNAME and settings.SMTP_PASSWORD and settings.SMTP_FROM
        and url.scheme == "https" and url.netloc and not url.query and not url.fragment)


def _send(recipient: str, token: str):
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = recipient
    message["Subject"] = "Подтвердите почту для регистрации в Регистре"
    link = settings.PUBLIC_APP_URL.rstrip("/") + "/#/verify-email?token=" + token
    message.set_content("Чтобы создать клиентский аккаунт в Регистре, откройте ссылку "
        "и задайте свой пароль:\n\n" + link + "\n\nСсылка действует 1 час и используется один раз. "
        "Если вы не запрашивали регистрацию, просто проигнорируйте письмо.")
    context = ssl.create_default_context()
    transport = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    kwargs = {"context": context} if settings.SMTP_USE_SSL else {}
    with transport(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10, **kwargs) as smtp:
        if not settings.SMTP_USE_SSL:
            smtp.starttls(context=context)
        smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)


async def send_confirmation_email(recipient: str, token: str):
    await asyncio.wait_for(asyncio.to_thread(_send, recipient, token), timeout=30)
