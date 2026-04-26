"""
BackendConnector abstraction.

Stella is one implementation among many. Future Shopify, WooCommerce, and
healthcare connectors implement the same interface; the agent's tools and the
order sync path are written against this abstraction, not against a specific
backend.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass
class ConnectorVariant:
    external_id: str
    sku: Optional[str]
    option1: Optional[str]
    option2: Optional[str]
    option3: Optional[str]
    price: Optional[float]
    inventory_quantity: Optional[int]
    available: bool
    image_url: Optional[str]
    raw: dict


@dataclass
class ConnectorProduct:
    external_id: str
    name: str
    description: Optional[str]
    price: Optional[float]
    currency: str
    images: list[str]
    variants: list[ConnectorVariant]
    categories: list[str]
    tags: list[str]
    url: Optional[str]
    in_stock: bool
    raw: dict


@dataclass
class ConnectorAvailability:
    available: bool
    quantity: Optional[int]
    price: Optional[float]
    variant_external_id: Optional[str]
    sku: Optional[str]


@dataclass
class ConnectorOrderLineItem:
    external_variant_id: Optional[str]
    external_product_id: Optional[str]
    name: str
    quantity: int
    unit_price: float
    option1: Optional[str] = None
    option2: Optional[str] = None
    option3: Optional[str] = None
    image_url: Optional[str] = None


@dataclass
class ConnectorOrderDraft:
    email: str
    phone: Optional[str]
    line_items: list[ConnectorOrderLineItem]
    subtotal: float
    total: float
    currency: str
    payment_method: str
    payment_intent_id: Optional[str]
    shipping_address: Optional[dict]
    billing_address: Optional[dict]
    note: Optional[str]


@dataclass
class ConnectorOrderReceipt:
    external_id: str
    external_order_number: str
    status: str
    payment_status: str
    created_at: str


class BackendConnector(ABC):
    """Abstract interface every backend integration must implement."""

    backend_type: str

    @abstractmethod
    async def list_products(
        self,
        updated_since: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> AsyncIterator[ConnectorProduct]:
        ...

    @abstractmethod
    async def get_product(self, external_id: str) -> ConnectorProduct:
        ...

    @abstractmethod
    async def check_availability(
        self,
        product_external_id: str,
        option1: Optional[str] = None,
        option2: Optional[str] = None,
        option3: Optional[str] = None,
    ) -> ConnectorAvailability:
        ...

    @abstractmethod
    async def create_order(
        self,
        draft: ConnectorOrderDraft,
        idempotency_key: str,
        correlation_id: Optional[str] = None,
    ) -> ConnectorOrderReceipt:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    async def register_webhook(self, url: str, events: list[str]) -> dict:
        raise NotImplementedError(f"{self.backend_type} does not support webhooks")

    async def list_webhooks(self) -> list[dict]:
        raise NotImplementedError
