"""
Connector registry. Future Shopify/Woo/healthcare connectors register here.
"""
from app.services.connectors.agenticom_connector import AgenticomConnector
from app.services.connectors.base import (
    BackendConnector,
    ConnectorAvailability,
    ConnectorOrderDraft,
    ConnectorOrderLineItem,
    ConnectorOrderReceipt,
    ConnectorProduct,
    ConnectorVariant,
)

_REGISTRY: dict[str, type[BackendConnector]] = {
    "stella": AgenticomConnector,
    "agenticom": AgenticomConnector,
}


def get_connector(backend_type: str, config: dict) -> BackendConnector:
    if backend_type not in _REGISTRY:
        raise ValueError(f"Unknown backend_type: {backend_type}")
    return _REGISTRY[backend_type](config)


__all__ = [
    "BackendConnector",
    "ConnectorAvailability",
    "ConnectorOrderDraft",
    "ConnectorOrderLineItem",
    "ConnectorOrderReceipt",
    "ConnectorProduct",
    "ConnectorVariant",
    "AgenticomConnector",
    "get_connector",
]
