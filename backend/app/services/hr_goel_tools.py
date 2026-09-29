"""
OpenAI function-calling tool definitions and executor for the HR Goel agent
(website_type == "it_solutions"). Public-receptionist class: anonymous
visitor, lead write only — never authenticated, no RBAC, no reads of other
tenants' data.

The only tool is `submit_quote`, which creates a lead in edgeX via its
public submit endpoint. See docs/orca-platform/hr-goel/HR-GOEL-AGENT-BRIEF.md
(brain folder) for the full contract.
"""
import logging
import re

import httpx

from app.config import get_settings

logger = logging.getLogger("zunkiree.hr_goel_tools")

TIMEOUT_SECONDS = 10.0
DEFAULT_DIAL = "+977"
MAX_BARE_NATIONAL = 10


def to_e164(raw: str | None, fallback_dial: str = DEFAULT_DIAL) -> str | None:
    """Best-effort E.164 normalization. Ported from clinic_tools.to_e164."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    had_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    if had_plus:
        return f"+{digits}"
    fb_digits = re.sub(r"\D", "", fallback_dial or DEFAULT_DIAL) or "977"
    if len(digits) <= MAX_BARE_NATIONAL:
        return f"{fb_digits if fb_digits.startswith('+') else '+' + fb_digits}{digits}"
    return f"+{digits}"


HR_GOEL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_quote",
            "description": (
                "Create a quotation lead for the visitor once you have the product they "
                "want quoted, their email, AND their phone number, and you have read the "
                "details back to them for confirmation. Only call this once per confirmed "
                "request. Never call it before all three fields are known."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product": {
                        "type": "string",
                        "description": "The product/service the visitor wants quoted (e.g. 'Shivam Cement', 'Dolphin Bitumen').",
                    },
                    "email": {"type": "string", "description": "Visitor's email address"},
                    "phone": {"type": "string", "description": "Visitor's phone number"},
                    "first_name": {"type": "string", "description": "Visitor's first name, if given"},
                },
                "required": ["product", "email", "phone"],
            },
        },
    },
]


async def execute_hr_goel_tool(tool_name: str, tool_args: dict, session_id: str) -> dict:
    if tool_name == "submit_quote":
        return await _submit_quote(session_id=session_id, **tool_args)
    return {"error": f"Unknown tool: {tool_name}"}


async def _submit_quote(
    session_id: str,
    product: str,
    email: str,
    phone: str,
    first_name: str = "",
) -> dict:
    settings = get_settings()

    base = (settings.edgex_stage_base or "").rstrip("/")
    tenant_slug = settings.edgex_hrgoel_tenant_slug
    form_slug = settings.edgex_hrgoel_form_slug
    integration_key = settings.edgex_hrgoel_integration_key

    if not (base and tenant_slug and form_slug and integration_key):
        logger.error(
            "[HR-GOEL-QUOTE] misconfigured: base_set=%s tenant_slug_set=%s form_slug_set=%s key_set=%s",
            bool(base), bool(tenant_slug), bool(form_slug), bool(integration_key),
        )
        return {
            "success": False,
            "message": "Sorry, I can't submit quote requests right now — our team has been notified. Please try again shortly or contact us directly.",
        }

    phone_e164 = to_e164(phone) or phone
    idempotency_key = f"{session_id}:{product}".strip().lower()[:200]

    payload = {
        "email": email,
        "phone": phone_e164,
        "custom_fields": {"product": product},
        "intake_source": "AI Assistant",
        "idempotency_key": idempotency_key,
    }
    if first_name:
        payload["first_name"] = first_name

    url = f"{base}/api/public/submit/{tenant_slug}/{form_slug}"
    logger.info(
        "[HR-GOEL-QUOTE] submitting session_id=%s product=%r idempotency_key=%s",
        session_id, product, idempotency_key,
    )

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {integration_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.TimeoutException:
        logger.error("[HR-GOEL-QUOTE] timeout session_id=%s", session_id)
        return {
            "success": False,
            "message": "Sorry, that took too long to go through. Could you try again in a moment, or share your details another way?",
        }
    except httpx.HTTPError as exc:
        logger.error("[HR-GOEL-QUOTE] request failed session_id=%s error=%s", session_id, exc)
        return {
            "success": False,
            "message": "Sorry, something went wrong submitting your request. Please try again shortly.",
        }

    if resp.status_code in (200, 201):
        try:
            body = resp.json()
        except ValueError:
            body = {}
        lead_id = body.get("lead_id")
        logger.info(
            "[HR-GOEL-QUOTE] success session_id=%s status=%s lead_id=%s",
            session_id, resp.status_code, lead_id,
        )
        return {
            "success": True,
            "lead_id": lead_id,
            "message": "Done — your quote request is in and a confirmation email is on its way.",
        }

    if resp.status_code in (401, 403):
        logger.error("[HR-GOEL-QUOTE] auth misconfig session_id=%s status=%s body=%s", session_id, resp.status_code, resp.text[:300])
        return {
            "success": False,
            "message": "Sorry, I can't submit quote requests right now — our team has been notified. Please try again shortly or contact us directly.",
        }

    if resp.status_code == 404:
        logger.error("[HR-GOEL-QUOTE] wrong slug session_id=%s body=%s", session_id, resp.text[:300])
        return {
            "success": False,
            "message": "Sorry, I can't submit quote requests right now — our team has been notified. Please try again shortly or contact us directly.",
        }

    if resp.status_code == 503:
        logger.error("[HR-GOEL-QUOTE] pipeline not configured session_id=%s body=%s", session_id, resp.text[:300])
        return {
            "success": False,
            "message": "Sorry, our quotation system is temporarily unavailable. Please share your details and we'll follow up, or try again shortly.",
        }

    logger.error(
        "[HR-GOEL-QUOTE] unexpected status session_id=%s status=%s body=%s",
        session_id, resp.status_code, resp.text[:300],
    )
    return {
        "success": False,
        "message": "Sorry, I couldn't submit that just now. Please try again shortly, or share your details and we'll follow up.",
    }
