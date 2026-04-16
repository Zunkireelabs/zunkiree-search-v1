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


async def send_welcome_email(to_email: str, customer_name: str, site_id: str, api_key: str) -> bool:
    """Send welcome email with API key and dashboard link to a new customer."""
    if not settings.smtp_username or not settings.smtp_password:
        logger.warning("[EMAIL] SMTP not configured, skipping welcome email to %s", to_email)
        return False

    dashboard_url = "https://zunkiree-search-panel.zunkireelabs.com"

    msg = EmailMessage()
    msg["Subject"] = "Welcome to Zunkiree Search — Your Dashboard Access"
    msg["From"] = settings.smtp_from_email or settings.smtp_username
    msg["To"] = to_email
    msg.set_content(
        f"Hi {customer_name},\n\n"
        f"Welcome to Zunkiree Search! Your AI search widget is ready.\n\n"
        f"Here are your dashboard credentials:\n\n"
        f"  Dashboard: {dashboard_url}\n"
        f"  Site ID:   {site_id}\n"
        f"  API Key:   {api_key}\n\n"
        f"Use the API key above to sign in to your dashboard where you can view:\n"
        f"  - Leads captured through your search widget\n"
        f"  - Query history and analytics\n"
        f"  - CSV exports of your data\n\n"
        f"Keep your API key safe — treat it like a password.\n\n"
        f"If you have any questions, reply to this email.\n\n"
        f"— Zunkiree Team"
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
        logger.info("[EMAIL] Welcome email sent to %s (site: %s)", to_email, site_id)
        return True
    except Exception as e:
        logger.error("[EMAIL] Failed to send welcome email to %s: %s", to_email, e)
        return False
