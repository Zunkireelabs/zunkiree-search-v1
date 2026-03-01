import logging
import aiosmtplib
from email.message import EmailMessage
from app.config import get_settings

logger = logging.getLogger("zunkiree.email.service")

settings = get_settings()


async def send_verification_email(to_email: str, code: str, brand_name: str) -> bool:
    """Send a verification code email. Returns True on success."""
    if not settings.smtp_username or not settings.smtp_password:
        logger.warning("[EMAIL] SMTP not configured, skipping send to %s (code: %s)", to_email, code)
        return False

    msg = EmailMessage()
    msg["Subject"] = f"Your verification code for {brand_name}"
    msg["From"] = settings.smtp_from_email or settings.smtp_username
    msg["To"] = to_email
    msg.set_content(
        f"Your verification code for {brand_name} is: {code}\n\n"
        f"This code expires in 10 minutes.\n\n"
        f"If you did not request this, please ignore this email."
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=True,
        )
        logger.info("[EMAIL] Verification code sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("[EMAIL] Failed to send to %s (code: %s): %s", to_email, code, e)
        return False
