"""
eSewa e-Payment v2 integration.
Handles payment initiation (form data + HMAC signature) and callback verification.
"""
import base64
import hashlib
import hmac
import json
import logging
import uuid

from app.config import get_settings

logger = logging.getLogger("zunkiree.esewa")
settings = get_settings()

SANDBOX_URL = "https://rc-epay.esewa.com.np/api/epay/main/v2/form"
PRODUCTION_URL = "https://epay.esewa.com.np/api/epay/main/v2/form"


def _sign(message: str, secret_key: str) -> str:
    """Generate HMAC-SHA256 signature, base64 encoded."""
    sig = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(sig).decode("utf-8")


def build_payment_form(
    total_amount: float,
    transaction_uuid: str,
    success_url: str,
    failure_url: str,
) -> dict:
    """
    Build the form data and payment URL for eSewa e-Payment v2.
    Returns { payment_url, form_data }.
    """
    merchant_code = settings.esewa_merchant_code
    secret_key = settings.esewa_secret_key

    signed_field_names = "total_amount,transaction_uuid,product_code"
    message = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={merchant_code}"
    signature = _sign(message, secret_key)

    form_data = {
        "amount": str(total_amount),
        "tax_amount": "0",
        "total_amount": str(total_amount),
        "transaction_uuid": transaction_uuid,
        "product_code": merchant_code,
        "product_service_charge": "0",
        "product_delivery_charge": "0",
        "success_url": success_url,
        "failure_url": failure_url,
        "signed_field_names": signed_field_names,
        "signature": signature,
    }

    payment_url = SANDBOX_URL if settings.esewa_sandbox else PRODUCTION_URL

    return {"payment_url": payment_url, "form_data": form_data}


def verify_callback(encoded_data: str) -> dict | None:
    """
    Verify an eSewa callback by decoding the base64 response data
    and checking the HMAC signature.
    Returns the decoded data dict if valid, None if invalid.
    """
    try:
        decoded = base64.b64decode(encoded_data).decode("utf-8")
        data = json.loads(decoded)
    except Exception:
        logger.error("Failed to decode eSewa callback data")
        return None

    # Verify signature
    signed_field_names = data.get("signed_field_names", "")
    fields = signed_field_names.split(",")
    message = ",".join(f"{f}={data.get(f, '')}" for f in fields)
    expected_sig = _sign(message, settings.esewa_secret_key)

    if data.get("signature") != expected_sig:
        logger.error("eSewa signature mismatch")
        return None

    return data
