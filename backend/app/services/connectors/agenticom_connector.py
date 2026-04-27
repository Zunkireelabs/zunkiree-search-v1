"""
AgenticomConnector — Stella backend implementation of BackendConnector.

Two wire modes:

- **legacy**: when only a global shared secret is available
  (`AGENTICOM_SYNC_SECRET` from `Settings`). Headers `X-Sync-Secret` +
  `X-Site-ID`, paths under `/api/sync/`. This is the Z1 wire — preserved
  byte-identically for any tenant that hasn't been migrated to per-tenant
  credentials. Zero-downtime migration depends on this.

- **v1**: when per-tenant `sync_key_id` + `sync_key_secret` are present in
  the config (issued by Stella per `SHARED-CONTRACT.md` §4). Headers
  `Authorization: Bearer <secret>` + `X-Stella-Site-Id`, paths under
  `/api/sync/v1/`.

Z3 contract additions:
- Every outbound call carries `X-Correlation-Id` from the contextvar
  (SHARED-CONTRACT §5).
- v1-mode `create_order` carries `Idempotency-Key` (SHARED-CONTRACT §6).
- v1-mode `search_products` falls back to legacy URL + `X-Sync-Secret`
  because Stella v1 has no search surface (locked decision Z3 §1.2 (b)).
"""
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import httpx

from app.config import get_settings
from app.services.connectors.base import (
    BackendConnector,
    ConnectorAvailability,
    ConnectorOrderDraft,
    ConnectorOrderReceipt,
    ConnectorProduct,
    ConnectorVariant,
)
from app.services.correlation import get_correlation_id

logger = logging.getLogger("zunkiree.connectors.agenticom")


class ConnectorRequestError(Exception):
    """Raised when the backend returns a non-success status."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Backend returned {status_code}: {body[:200]}")


class AgenticomConnector(BackendConnector):
    backend_type = "stella"

    _ORDER_TIMEOUT = 10.0
    _PRODUCT_TIMEOUT = 8.0

    def __init__(self, config: dict):
        self._api_url = (config.get("api_url") or "").rstrip("/")
        self._remote_site_id = config.get("remote_site_id") or ""

        sync_key_id = config.get("sync_key_id") or ""
        sync_key_secret = config.get("sync_key_secret") or ""
        legacy_secret = config.get("legacy_shared_secret") or ""

        if sync_key_id and sync_key_secret:
            self.mode = "v1"
            self._sync_key_id = sync_key_id
            self._sync_key_secret = sync_key_secret
            self._legacy_secret = ""
        elif legacy_secret:
            self.mode = "legacy"
            self._sync_key_id = ""
            self._sync_key_secret = ""
            self._legacy_secret = legacy_secret
        else:
            self.mode = "unconfigured"
            self._sync_key_id = ""
            self._sync_key_secret = ""
            self._legacy_secret = ""

    def _path_prefix(self) -> str:
        return "/api/sync/v1" if self.mode == "v1" else "/api/sync"

    def _auth_headers(self) -> dict:
        if self.mode == "v1":
            return {
                "Authorization": f"Bearer {self._sync_key_secret}",
                "X-Stella-Site-Id": self._remote_site_id,
            }
        return {
            "X-Sync-Secret": self._legacy_secret,
            "X-Site-ID": self._remote_site_id,
        }

    def _legacy_search_headers(self) -> dict:
        """Legacy auth headers for the v1-mode `search_products` fallback.

        Stella v1 has no search surface, so v1-credentialed tenants still hit
        `/api/sync/products?search=...` with the global `X-Sync-Secret` for
        this one method (locked Z3 §1.2 (b)). Reads `agenticom_sync_secret`
        from settings rather than relying on the connector's stored
        `_legacy_secret`, which is cleared in v1 mode by `__init__`.
        """
        settings = get_settings()
        return {
            "X-Sync-Secret": settings.agenticom_sync_secret or "",
            "X-Site-ID": self._remote_site_id,
        }

    def _with_correlation(self, headers: dict) -> dict:
        """Stamp X-Correlation-Id on every outbound request (SHARED-CONTRACT §5)."""
        return {**headers, "X-Correlation-Id": get_correlation_id()}

    def _is_configured(self) -> bool:
        return self.mode != "unconfigured" and bool(self._api_url)

    async def health_check(self) -> bool:
        return self._is_configured() and bool(self._remote_site_id)

    async def list_products(
        self,
        updated_since: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> AsyncIterator[ConnectorProduct]:
        if not self._is_configured():
            return
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if updated_since:
            params["updated_since"] = updated_since

        async with httpx.AsyncClient(timeout=self._PRODUCT_TIMEOUT) as client:
            resp = await client.get(
                f"{self._api_url}{self._path_prefix()}/products",
                params=params,
                headers=self._with_correlation(self._auth_headers()),
            )
            if resp.status_code != 200:
                raise ConnectorRequestError(resp.status_code, resp.text)
            for raw in resp.json().get("products", []):
                yield self._product_from_raw(raw)

    async def get_product(self, external_id: str) -> ConnectorProduct:
        raise NotImplementedError(
            "AgenticomConnector.get_product not yet implemented "
            "(Stella legacy /api/sync surface is search-based; arrives with v1 wire in Z3)"
        )

    async def check_availability(
        self,
        product_external_id: str,
        option1: Optional[str] = None,
        option2: Optional[str] = None,
        option3: Optional[str] = None,
    ) -> ConnectorAvailability:
        raise NotImplementedError(
            "AgenticomConnector.check_availability not yet implemented "
            "(arrives with v1 wire in Z3)"
        )

    async def search_products(
        self,
        query: str,
        limit: int = 10,
        in_stock_only: bool = True,
    ) -> list[ConnectorProduct]:
        """Search the Stella storefront in real-time. Used by the agent's tools.

        v1-mode tenants fall back to the legacy URL + `X-Sync-Secret` because
        Stella v1 has no search surface. All other v1-mode methods (get_product,
        check_availability, create_order) use the v1 path + Bearer auth.
        Locked decision Z3 §1.2 (b) — temporary until post-migration cleanup
        retires the global secret per ZUNKIREE-IMPLEMENTATION §8.
        """
        if not self._is_configured():
            return []
        params: dict = {"search": query, "limit": limit}
        if in_stock_only:
            params["in_stock"] = "true"

        if self.mode == "v1":
            url = f"{self._api_url}/api/sync/products"
            headers = self._with_correlation(self._legacy_search_headers())
        else:
            url = f"{self._api_url}{self._path_prefix()}/products"
            headers = self._with_correlation(self._auth_headers())

        async with httpx.AsyncClient(timeout=self._PRODUCT_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                raise ConnectorRequestError(resp.status_code, resp.text)
            return [
                self._product_from_raw(raw)
                for raw in resp.json().get("products", [])
            ]

    async def create_order(
        self,
        draft: ConnectorOrderDraft,
        idempotency_key: str,
        correlation_id: Optional[str] = None,
    ) -> ConnectorOrderReceipt:
        if not self._is_configured():
            raise ConnectorRequestError(0, "Agenticom sync not configured")

        line_items: list[dict] = []
        for li in draft.line_items:
            row: dict = {
                "quantity": li.quantity,
                "name": li.name,
                "price": li.unit_price,
            }
            if li.image_url:
                row["image_url"] = li.image_url
            if li.external_product_id:
                row["product_id"] = li.external_product_id
            if li.option1:
                row["size"] = li.option1
            if li.option2:
                row["color"] = li.option2
            line_items.append(row)

        payload: dict = {
            "email": draft.email,
            "phone": draft.phone,
            "line_items": line_items,
            "shipping_address": draft.shipping_address,
            "payment_method": draft.payment_method,
            "payment_intent_id": draft.payment_intent_id,
            "note": draft.note,
            "subtotal": draft.subtotal,
            "total": draft.total,
            "currency": draft.currency,
        }

        # Idempotency-Key is v1-only per SHARED-CONTRACT §6 — the legacy
        # /api/sync/orders endpoint does not understand it.
        order_headers: dict = {
            **self._auth_headers(),
            "Content-Type": "application/json",
        }
        if self.mode == "v1" and idempotency_key:
            order_headers["Idempotency-Key"] = idempotency_key

        async with httpx.AsyncClient(timeout=self._ORDER_TIMEOUT) as client:
            resp = await client.post(
                f"{self._api_url}{self._path_prefix()}/orders",
                json=payload,
                headers=self._with_correlation(order_headers),
            )

        if resp.status_code != 201:
            raise ConnectorRequestError(resp.status_code, resp.text)

        body = resp.json() if resp.content else {}
        return ConnectorOrderReceipt(
            external_id=str(body.get("id") or body.get("order_number") or ""),
            external_order_number=str(body.get("order_number") or ""),
            status=str(body.get("status") or ""),
            payment_status=str(body.get("payment_status") or ""),
            created_at=str(body.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )

    @staticmethod
    def _product_from_raw(p: dict) -> ConnectorProduct:
        variants_raw = p.get("variants") or []
        variants: list[ConnectorVariant] = []
        for v in variants_raw:
            variants.append(
                ConnectorVariant(
                    external_id=str(v.get("id") or ""),
                    sku=v.get("sku"),
                    option1=v.get("size") or v.get("option1"),
                    option2=v.get("color") or v.get("option2"),
                    option3=v.get("option3"),
                    price=v.get("price"),
                    inventory_quantity=v.get("inventory_quantity"),
                    available=bool(v.get("available", True)),
                    image_url=(v.get("image") or {}).get("url") if isinstance(v.get("image"), dict) else v.get("image_url"),
                    raw=v,
                )
            )

        # Match the legacy fallback in tools.py: top-level price falls through
        # to the first variant's price when absent.
        price = p.get("price")
        if price is None and variants_raw:
            price = (variants_raw[0] or {}).get("price")

        return ConnectorProduct(
            external_id=str(p.get("id") or ""),
            name=p.get("name", ""),
            description=p.get("description"),
            price=price,
            currency=p.get("currency", "NPR"),
            images=[img.get("url", "") for img in (p.get("images") or [])],
            variants=variants,
            categories=p.get("categories") or [],
            tags=p.get("tags") or [],
            url=p.get("url"),
            in_stock=bool(p.get("in_stock", True)),
            raw=p,
        )
