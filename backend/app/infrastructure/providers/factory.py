"""
Provider Factory — creates the appropriate TrademarkRegistryProvider based on config.

Supported provider types:
    - "mock"  → MockFipsProvider (in-memory, no network)
    - "fips"  → (future) Real FIPS/Роспатент HTTP provider
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.infrastructure.providers.base import TrademarkRegistryProvider


class ProviderFactory:
    """
    Factory for creating TrademarkRegistryProvider instances.

    Config shape:
        {
            "provider": "mock" | "fips",
            # For real FIPS provider (future):
            "base_url": "https://www1.fips.ru/",
            "api_key":  "...",
            "timeout":  30.0,
        }
    """

    @staticmethod
    def create(config: dict) -> "TrademarkRegistryProvider":
        provider_type: str = config.get("provider", "mock").lower()

        if provider_type == "mock":
            from app.infrastructure.providers.mock_fips import MockFipsProvider

            return MockFipsProvider()

        if provider_type == "fips":
            # Placeholder — real FIPS integration would go here
            raise NotImplementedError(
                "Real FipsProvider is not yet implemented. "
                "Set provider='mock' for development."
            )

        raise ValueError(
            f"Unknown registry provider type: '{provider_type}'. "
            "Supported values: mock, fips."
        )
