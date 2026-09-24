"""
The ONLY file that knows ClinicMD's schema/RPC surface.

ClinicMD has no server API — its public booking flow runs entirely in the
browser against Supabase (RLS + SECURITY DEFINER RPCs + DB triggers) using
the anon key. This client makes exactly those same anon calls, so it gets
no more privilege than any website visitor and every DB guard (chair
capacity P0003, branch online capacity P0005, datetime triggers) still
applies.

Mirrors clinic-md/src/services/api.js. Anon key only — never service_role.
"""
import contextvars
import logging
import uuid
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("zunkiree.clinicmd_client")

# Already bounded — every httpx.AsyncClient call in this file passes this as
# its timeout (see _get/_post_rpc/insert_booking below). Reviewed under P2
# brief §7c B4 alongside the OpenAI/Pinecone timeout audit; no change needed.
TIMEOUT_SECONDS = 10.0

# ClinicMD org the current task is acting for. Set by clinic_tools._resolve_org;
# logged on every client call so tenant isolation is provable from logs.
current_org_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("clinicmd_org_id", default=None)


def _log_call(op: str, org_id: str | None = None, **ids: Any) -> None:
    extra = "".join(f" {k}={v}" for k, v in ids.items() if v)
    logger.info("[CLINICMD] call op=%s org_id=%s%s", op, org_id or current_org_id.get() or "-", extra)


class ClinicMdError(Exception):
    """Base error for ClinicMD client failures."""

    def __init__(self, message: str, code: str | None = None, pg_code: str | None = None):
        super().__init__(message)
        self.code = code
        self.pg_code = pg_code


class ClinicMdNotConfigured(ClinicMdError):
    def __init__(self):
        super().__init__("ClinicMD integration is not configured for this environment.", code="NOT_CONFIGURED")


class ClinicMdClient:
    def __init__(self, base_url: str, anon_key: str):
        self.base_url = base_url.rstrip("/")
        self.anon_key = anon_key

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        explicit_org = str(params.get("org_id", "")).removeprefix("eq.") or None
        _log_call(f"GET {path}", explicit_org, slug=str(params.get("slug", "")).removeprefix("eq."),
                  branch_id=str(params.get("branch_id", "")).removeprefix("eq."))
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(f"{self.base_url}{path}", params=params, headers=self._headers())
        self._raise_for_status(resp)
        return resp.json()

    async def _post_rpc(self, fn_name: str, payload: dict[str, Any]) -> Any:
        _log_call(f"rpc {fn_name}", payload.get("p_org_id"), branch_id=payload.get("p_branch_id"),
                  booking_id=payload.get("p_booking_id"))
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{self.base_url}/rest/v1/rpc/{fn_name}", json=payload, headers=self._headers()
            )
        self._raise_for_status(resp)
        return resp.json()

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        pg_code = None
        message = resp.text
        try:
            body = resp.json()
            if isinstance(body, dict):
                message = body.get("message") or message
                pg_code = body.get("code")
        except ValueError:
            pass
        logger.warning("[CLINICMD] request failed status=%s pg_code=%s", resp.status_code, pg_code)
        raise ClinicMdError(message, pg_code=pg_code)

    # --- Reads ---

    async def get_org(self, slug: str) -> dict | None:
        rows = await self._get(
            "/rest/v1/organizations",
            {"slug": f"eq.{slug}", "is_active": "eq.true", "select": "id,name,slug,settings"},
        )
        return rows[0] if rows else None

    async def list_branches(self, org_id: str) -> list[dict]:
        return await self._get(
            "/rest/v1/branches",
            {
                "org_id": f"eq.{org_id}",
                "is_active": "eq.true",
                "select": "id,name,address,phone,timezone,excluded_treatment_categories",
            },
        )

    async def list_treatments(self, org_id: str, branch: dict | None = None) -> list[dict]:
        treatments = await self._get(
            "/rest/v1/treatments",
            {
                "org_id": f"eq.{org_id}",
                "is_active": "eq.true",
                "select": "id,name,duration_minutes,price_npr,description,category",
                "order": "name",
            },
        )
        excluded = set((branch or {}).get("excluded_treatment_categories") or [])
        if excluded:
            treatments = [t for t in treatments if t.get("category") not in excluded]
        return treatments

    async def list_chairs(self, branch_id: str) -> list[dict]:
        return await self._get(
            "/rest/v1/chairs",
            {"branch_id": f"eq.{branch_id}", "is_active": "eq.true", "select": "id,name,capacity"},
        )

    async def bookings_range(self, branch_id: str, start_date: str, end_date: str) -> list[dict]:
        result = await self._post_rpc(
            "public_check_branch_bookings_range",
            {"p_branch_id": branch_id, "p_start_date": start_date, "p_end_date": end_date},
        )
        return result or []

    # --- Writes ---

    async def upsert_customer(
        self,
        org_id: str,
        branch_id: str,
        full_name: str,
        phone: str,
        email: str | None,
        gender: str | None,
    ) -> str | None:
        try:
            result = await self._post_rpc(
                "upsert_customer_for_booking",
                {
                    "p_org_id": org_id,
                    "p_branch_id": branch_id,
                    "p_full_name": full_name,
                    "p_phone": phone,
                    "p_email": email,
                    "p_gender": gender,
                },
            )
            return result
        except ClinicMdError as e:
            # Customer-link failure is non-blocking (matches web behavior).
            logger.warning("[CLINICMD] upsert_customer_for_booking failed, continuing without link: %s", e.pg_code)
            return None

    async def insert_booking(self, row: dict[str, Any]) -> None:
        _log_call("POST /rest/v1/bookings", None, branch_id=row.get("branch_id"), booking_id=row.get("id"))
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{self.base_url}/rest/v1/bookings",
                json=row,
                headers=self._headers(prefer="return=minimal"),
            )
        self._raise_for_status(resp)

    async def get_booking(self, booking_id: str) -> dict | None:
        result = await self._post_rpc("public_get_booking_by_id", {"p_booking_id": booking_id})
        if isinstance(result, list):
            return result[0] if result else None
        return result


def new_booking_id() -> str:
    return str(uuid.uuid4())


_clinicmd_client: ClinicMdClient | None = None


def get_clinicmd_client() -> ClinicMdClient:
    """Returns the singleton client, or raises ClinicMdNotConfigured if env is unset."""
    global _clinicmd_client
    if _clinicmd_client is None:
        settings = get_settings()
        if not settings.clinicmd_supabase_url or not settings.clinicmd_supabase_anon_key:
            raise ClinicMdNotConfigured()
        _clinicmd_client = ClinicMdClient(settings.clinicmd_supabase_url, settings.clinicmd_supabase_anon_key)
    return _clinicmd_client
