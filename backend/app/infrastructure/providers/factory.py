"""
Provider Factory — creates the appropriate TrademarkRegistryProvider based on config.

Supported provider types:
    - "mock"  → MockFipsProvider (in-memory, no network)
    - "fips" / "rospatent" → official Rospatent Search Platform API
    - "rospatent_public" → limited anonymous public Search Platform UI
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
            "provider": "mock" | "fips" | "rospatent_public",
            "base_url": "https://searchplatform.rospatent.gov.ru/patsearch/v0.2/",
            "api_key":  "...",
            "trademark_datasets": ["..."],
            "application_datasets": ["..."],
            "timeout":  30.0,
        }
    """

    @staticmethod
    def create(config) -> "TrademarkRegistryProvider":
        # Backwards-compat: accept either a string ("mock"/"fips") or a dict.
        if isinstance(config, str):
            provider_type = config.lower()
            cfg: dict = {}
        else:
            config = config or {}
            provider_type = str(config.get("provider", "mock")).lower()
            cfg = config

        if provider_type == "mock":
            from app.infrastructure.providers.mock_fips import MockFipsProvider
            return MockFipsProvider()

        if provider_type in ("fips", "rospatent"):
            from app.infrastructure.providers.rospatent import RospatentSearchProvider

            return RospatentSearchProvider(
                api_key=str(cfg.get("api_key") or ""),
                base_url=str(
                    cfg.get("base_url")
                    or "https://searchplatform.rospatent.gov.ru/patsearch/v0.2/"
                ),
                trademark_datasets=list(cfg.get("trademark_datasets") or []),
                application_datasets=list(cfg.get("application_datasets") or []),
                class_filter_field=str(
                    cfg.get("class_filter_field") or "classification.icgs"
                ),
                timeout=float(cfg.get("timeout") or 30.0),
                verify_ssl=bool(cfg.get("verify_ssl", True)),
                client=cfg.get("client"),
            )

        if provider_type in ("rospatent_public", "fips_public", "public"):
            from app.infrastructure.providers.rospatent_public import (
                RospatentPublicSearchProvider,
            )

            return RospatentPublicSearchProvider(
                base_url=str(
                    cfg.get("public_base_url")
                    or "https://searchplatform.rospatent.gov.ru/"
                ),
                data_sources=list(cfg.get("public_data_sources") or []),
                timeout=float(cfg.get("timeout") or 30.0),
                verify_ssl=bool(cfg.get("verify_ssl", True)),
                max_results=int(cfg.get("public_max_results") or 100),
                page_size=int(cfg.get("public_page_size") or 50),
                min_interval=float(cfg.get("public_min_interval") or 0.75),
                client=cfg.get("client"),
            )

        raise ValueError(
            f"Unknown registry provider type: '{provider_type}'. "
            "Supported values: mock, fips, rospatent_public."
        )
