"""
The ONLY file that knows Zennly's schema/RPC surface.

Zennly (`Zunkireelabs/book-spa`, local `~/Projects/bookX`) is ClinicMD's parent
fork — same anon public-booking architecture (RLS + SECURITY DEFINER RPCs + DB
triggers), reached with the anon key only, never service_role. Mirrors stage
book-spa's `src/services/api.js` (sha a12f17c, 2026-10-05):

- `get_org`      -> fetchOrganizationBySlug (api.js:9500): org + its
                    `industries` join, which is the backend-provided
                    vocabulary (staff_label_plural, location_label_plural) —
                    SBAL-Z1-ZENNLY-BACKEND-BRIEF item 3 ("dentist/chair/
                    treatment must not leak into a salon conversation").
- `list_branches`-> fetchBranchesByOrgId (api.js:9541).
- `list_treatments` -> fetchBookableServicesByOrgSlug (api.js:9600), RPC
                    `public_get_bookable_services` (migration-205) — takes the
                    org SLUG, not org_id, so the slug seen in get_org is
                    remembered per org_id for this call.
- `list_chairs`  -> fetchRooms (api.js:228): a direct anon SELECT on `rooms`
                    (migration-093 grants anon read on active rooms) — same
                    shape ClinicMD's chairs are read in, so clinic_availability
                    (which only ever reads a "chair"'s `id`/`capacity`) needs
                    no changes to consume either backend's resource.
- `bookings_range` -> fetchBranchAvailabilityWindow (api.js:248), RPC
                    `public_check_branch_bookings_range` (migration-131,
                    SAME NAME ClinicMD's RPC mirrors) — returns `room_id`, not
                    `chair_id`; remapped to `chair_id` here so
                    clinic_availability.build_occupancy/find_available_chair
                    (which key occupancy by `booking["chair_id"]`) work
                    unmodified against a Zennly tenant.
- `upsert_customer` -> createBooking's customer-dedupe step (api.js:5353):
                    `find_customer_for_booking` RPC (migration-098, anon-safe)
                    then a direct anon INSERT into `customers`
                    (`anon_insert_customers`, migration-008). Non-blocking on
                    failure, same as ClinicMD's `upsert_customer_for_booking`.
- `insert_booking` -> createBooking's public/`orgSlug` insert path
                    (api.js:5519-5610): `Prefer: return=minimal` (anon has no
                    SELECT on `bookings` since migration-097) and a
                    `client_request_id` for the read-back below.
                    `created_by` stays None — Zennly's own dashboard shows a
                    booking as "Online booking" purely from
                    `created_by IS NULL` (CalendarGrid.jsx:919,
                    `isOnline: !b.created_by`), so leaving it unset here IS
                    the marker the brief asks for; there is no separate badge
                    column.
- `get_booking`  -> `public_get_booking_by_request_id` RPC (migration-223),
                    keyed on the same `client_request_id` the insert carried
                    — Zennly's anon callers can't SELECT a freshly-inserted
                    booking row directly, unlike ClinicMD's
                    `public_get_booking_by_id`.
"""
import contextvars
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("zunkiree.zennly_client")

TIMEOUT_SECONDS = 10.0

current_org_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("zennly_org_id", default=None)

DEFAULT_STAFF_LABEL_PLURAL = "staff"
DEFAULT_LOCATION_LABEL_PLURAL = "rooms"


def _log_call(op: str, org_id: str | None = None, **ids: Any) -> None:
    extra = "".join(f" {k}={v}" for k, v in ids.items() if v)
    logger.info("[ZENNLY] call op=%s org_id=%s%s", op, org_id or current_org_id.get() or "-", extra)


class ZennlyError(Exception):
    """Base error for Zennly client failures."""

    def __init__(self, message: str, code: str | None = None, pg_code: str | None = None):
        super().__init__(message)
        self.code = code
        self.pg_code = pg_code


class ZennlyNotConfigured(ZennlyError):
    def __init__(self):
        super().__init__("Zennly integration is not configured for this environment.", code="NOT_CONFIGURED")


class ZennlyClient:
    def __init__(self, base_url: str, anon_key: str):
        self.base_url = base_url.rstrip("/")
        self.anon_key = anon_key
        # org_id -> slug, filled by get_org. public_get_bookable_services takes
        # the slug, but clinic_tools._resolve_org only ever carries org_id past
        # that first call — this is how list_treatments recovers it.
        self._slug_by_org_id: dict[str, str] = {}

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
        _log_call(f"rpc {fn_name}", payload.get("p_org_id"), org_slug=payload.get("p_org_slug"),
                  branch_id=payload.get("p_branch_id"))
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
        logger.warning("[ZENNLY] request failed status=%s pg_code=%s", resp.status_code, pg_code)
        raise ZennlyError(message, pg_code=pg_code)

    # --- Reads ---

    async def get_org(self, slug: str) -> dict | None:
        rows = await self._get(
            "/rest/v1/organizations",
            {
                "slug": f"eq.{slug}",
                "is_active": "eq.true",
                "select": (
                    "id,name,slug,industry_type,"
                    "industries(staff_label,staff_label_plural,location_label,"
                    "location_label_plural,enable_rooms)"
                ),
            },
        )
        if not rows:
            return None
        org = dict(rows[0])
        industries = org.pop("industries", None) or {}
        org["staff_label_plural"] = industries.get("staff_label_plural") or DEFAULT_STAFF_LABEL_PLURAL
        org["location_label_plural"] = industries.get("location_label_plural") or DEFAULT_LOCATION_LABEL_PLURAL
        org["enable_rooms"] = industries.get("enable_rooms", True)
        self._slug_by_org_id[org["id"]] = slug
        return org

    async def list_branches(self, org_id: str) -> list[dict]:
        return await self._get(
            "/rest/v1/branches",
            {
                "org_id": f"eq.{org_id}",
                "is_active": "eq.true",
                "select": "id,name,address,phone,timezone,excluded_service_categories",
            },
        )

    async def list_treatments(self, org_id: str, branch: dict | None = None) -> list[dict]:
        slug = self._slug_by_org_id.get(org_id)
        if not slug:
            raise ZennlyError("Zennly org slug not resolved — call get_org first.", code="ORG_SLUG_UNRESOLVED")
        rows = await self._post_rpc("public_get_bookable_services", {"p_org_slug": slug})
        services = [
            {
                "id": s["id"],
                "name": s["name"],
                "duration_minutes": s.get("duration_minutes"),
                # effective_price_npr is offer/campaign-aware — the actual price a
                # booking right now charges, which is what list_services/
                # check_availability must quote (same field the public booking
                # flow itself displays).
                "price_npr": s.get("effective_price_npr", s.get("price_npr")),
                "description": s.get("description"),
                "category": s.get("category_name"),
            }
            for s in (rows or [])
        ]
        excluded = set((branch or {}).get("excluded_service_categories") or [])
        if excluded:
            services = [s for s in services if s.get("category") not in excluded]
        return services

    async def list_chairs(self, branch_id: str) -> list[dict]:
        return await self._get(
            "/rest/v1/rooms",
            {"branch_id": f"eq.{branch_id}", "is_active": "eq.true", "select": "id,name,capacity"},
        )

    async def list_therapists(self, branch_id: str) -> list[dict]:
        """SBAL-Z1 follow-up: enable_rooms=false orgs (e.g. SBAL — a salon
        with no fixed stations) have no `rooms` rows at all; capacity for
        them comes from active therapist headcount by gender instead.
        Mirrors DateTimeSelection.jsx's own therapist-count fetch exactly
        (api.js has no sibling function for this — the page queries
        `therapists` directly): `.select('gender').eq('branch_id', ...)
        .eq('is_active', true)` (DateTimeSelection.jsx:33-37)."""
        return await self._get(
            "/rest/v1/therapists",
            {"branch_id": f"eq.{branch_id}", "is_active": "eq.true", "select": "id,name,gender"},
        )

    async def bookings_range(self, branch_id: str, start_date: str, end_date: str) -> list[dict]:
        rows = await self._post_rpc(
            "public_check_branch_bookings_range",
            {"p_branch_id": branch_id, "p_start_date": start_date, "p_end_date": end_date},
        )
        # room_id -> chair_id: see module docstring. clinic_availability is
        # backend-agnostic and only ever reads "chair_id". therapist_gender
        # (migration-131's own RPC column, LEFT JOINed from therapists) is
        # passed through unchanged — build_gender_occupancy reads it
        # directly for enable_rooms=false tenants.
        return [{**row, "chair_id": row.get("room_id")} for row in (rows or [])]

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
            existing = await self._post_rpc(
                "find_customer_for_booking", {"p_org_id": org_id, "p_phone": phone, "p_email": email}
            )
            if existing:
                row = existing[0] if isinstance(existing, list) else existing
                if row and row.get("id"):
                    return row["id"]

            _log_call("POST /rest/v1/customers", org_id, branch_id=branch_id)
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{self.base_url}/rest/v1/customers",
                    json={
                        "org_id": org_id,
                        "branch_id": branch_id,
                        "full_name": full_name,
                        "phone": phone,
                        "email": email,
                        "gender": gender,
                    },
                    headers=self._headers(prefer="return=representation"),
                )
            self._raise_for_status(resp)
            rows = resp.json()
            return rows[0]["id"] if rows else None
        except ZennlyError as e:
            # Customer-link failure is non-blocking (matches ClinicMD and the
            # web flow: booking still proceeds, just without a linked profile).
            logger.warning("[ZENNLY] upsert_customer failed, continuing without link: %s", e.pg_code)
            return None

    async def insert_booking(self, row: dict[str, Any]) -> None:
        _log_call("POST /rest/v1/bookings", None, branch_id=row.get("branch_id"))
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{self.base_url}/rest/v1/bookings",
                json=row,
                headers=self._headers(prefer="return=minimal"),
            )
        self._raise_for_status(resp)

    async def get_booking(self, client_request_id: str) -> dict | None:
        result = await self._post_rpc(
            "public_get_booking_by_request_id", {"p_client_request_id": client_request_id}
        )
        if isinstance(result, list):
            return result[0] if result else None
        return result


_zennly_client: ZennlyClient | None = None


def get_zennly_client() -> ZennlyClient:
    """Returns the singleton client, or raises ZennlyNotConfigured if env is unset."""
    global _zennly_client
    if _zennly_client is None:
        settings = get_settings()
        if not settings.zennly_supabase_url or not settings.zennly_supabase_anon_key:
            raise ZennlyNotConfigured()
        _zennly_client = ZennlyClient(settings.zennly_supabase_url, settings.zennly_supabase_anon_key)
    return _zennly_client
