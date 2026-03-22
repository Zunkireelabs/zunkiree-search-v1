"""
Khalti e-Payment v2 integration.
Handles payment initiation and lookup/verification via Khalti API.
"""
import logging
import httpx

from app.config import get_settings

logger = logging.getLogger("zunkiree.khalti")
settings = get_settings()

SANDBOX_BASE = "https://a.khalti.com/api/v2"
PRODUCTION_BASE = "https://khalti.com/api/v2"


def _base_url() -> str:
    return SANDBOX_BASE if settings.khalti_sandbox else PRODUCTION_BASE


def _headers() -> dict:
    return {
        "Authorization": f"key {settings.khalti_secret_key}",
        "Content-Type": "application/json",
    }


async def initiate_payment(
    amount_npr: float,
    purchase_order_id: str,
    purchase_order_name: str,
    return_url: str,
    website_url: str = "https://zunkireelabs.com",
    customer_info: dict | None = None,
) -> dict:
    """
    Initiate a Khalti e-payment.
    amount_npr: amount in NPR (will be converted to paisa).
    Returns { pidx, payment_url } on success, { error } on failure.
    """
    amount_paisa = int(amount_npr * 100)

    payload = {
        "return_url": return_url,
        "website_url": website_url,
        "amount": amount_paisa,
        "purchase_order_id": purchase_order_id,
        "purchase_order_name": purchase_order_name,
    }
    if customer_info:
        payload["customer_info"] = customer_info

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base_url()}/epayment/initiate/",
                json=payload,
                headers=_headers(),
            )
            data = resp.json()

            if resp.status_code == 200 and "payment_url" in data:
                logger.info("Khalti payment initiated: pidx=%s", data.get("pidx"))
                return {
                    "pidx": data["pidx"],
                    "payment_url": data["payment_url"],
                }
            else:
                error_msg = data.get("detail", str(data))
                logger.error("Khalti initiation failed: %s", error_msg)
                return {"error": f"Khalti error: {error_msg}"}
    except Exception as e:
        logger.exception("Khalti initiation error: %s", e)
        return {"error": f"Khalti connection error: {str(e)}"}


async def lookup_payment(pidx: str) -> dict:
    """
    Verify/lookup a Khalti payment by pidx.
    Returns { status, transaction_id, total_amount, ... } on success.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base_url()}/epayment/lookup/",
                json={"pidx": pidx},
                headers=_headers(),
            )
            data = resp.json()

            if resp.status_code == 200:
                return data
            else:
                error_msg = data.get("detail", str(data))
                logger.error("Khalti lookup failed: %s", error_msg)
                return {"error": error_msg}
    except Exception as e:
        logger.exception("Khalti lookup error: %s", e)
        return {"error": str(e)}
