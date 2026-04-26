"""
AgenticomConnector — Stella backend implementation of BackendConnector.

Z1 wraps the existing Stella sync wire (legacy `/api/sync/*` endpoints with
`X-Sync-Secret` + `X-Site-ID` headers) inside the BackendConnector
abstraction. Wire behavior is unchanged from what previously lived inline in
`order.py` and `tools.py`. The v1 wire migration (`/api/sync/v1/*` with
per-tenant Bearer auth, idempotency keys, correlation IDs) lands in Z3.
"""
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import httpx

from app.services.connectors.base import (
    BackendConnector,
    ConnectorAvailability,
    ConnectorOrderDraft,
    ConnectorOrderReceipt,
    ConnectorProduct,
    ConnectorVariant,
)

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
        self._sync_secret = config.get("legacy_shared_secret") or ""
        self._remote_site_id = config.get("remote_site_id") or ""

    def _legacy_headers(self) -> dict:
        return {
            "X-Sync-Secret": self._sync_secret,
            "X-Site-ID": self._remote_site_id,
        }

    def _is_configured(self) -> bool:
        return bool(self._api_url and self._sync_secret)

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
                f"{self._api_url}/api/sync/products",
                params=params,
                headers=self._legacy_headers(),
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
        """Search the Stella storefront in real-time. Used by the agent's tools."""
        if not self._is_configured():
            return []
        params: dict = {"search": query, "limit": limit}
        if in_stock_only:
            params["in_stock"] = "true"

        async with httpx.AsyncClient(timeout=self._PRODUCT_TIMEOUT) as client:
            resp = await client.get(
                f"{self._api_url}/api/sync/products",
                params=params,
                headers=self._legacy_headers(),
            )
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
        # Z1 keeps the legacy wire shape verbatim; idempotency_key and
        # correlation_id are accepted on the interface but not yet sent on
        # headers (that's Z3's job, alongside the v1 endpoint switch).
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

        async with httpx.AsyncClient(timeout=self._ORDER_TIMEOUT) as client:
            resp = await client.post(
                f"{self._api_url}/api/sync/orders",
                json=payload,
                headers={**self._legacy_headers(), "Content-Type": "application/json"},
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
