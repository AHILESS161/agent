"""Общие FastAPI-зависимости: провайдеры LLM, prompt-реестр, реестр ТЗ.

Единственный источник правды. Раньше эти функции дублировались в
``endpoints/applications.py`` и ``endpoints/mvp.py``, а ``endpoints/intake.py``
импортировал их отсюда — но модуля не существовало, из-за чего приложение
не импортировалось вовсе.

Все настройки читаются из ``Settings`` (environment variables), никаких
значений, зашитых в код.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any


def _get_llm_provider() -> Any:
    """Вернуть LLM-провайдер согласно конфигурации.

    provider/base_url/api_key/model берутся из Settings и передаются в
    LLMProviderFactory, поэтому переменные окружения всегда побеждают
    значения по умолчанию внутри фабрики.
    """
    from app.core.config import settings
    from app.infrastructure.llm.factory import LLMProviderFactory

    config: dict[str, Any] = {
        "provider": settings.LLM_PROVIDER,
        "base_url": getattr(settings, "LLM_BASE_URL", None),
        "api_key": getattr(settings, "LLM_API_KEY", None),
        "model": getattr(settings, "LLM_MODEL", None),
        "authorization_key": getattr(settings, "GIGACHAT_AUTHORIZATION_KEY", None),
        "scope": getattr(settings, "GIGACHAT_SCOPE", None),
        "auth_url": getattr(settings, "GIGACHAT_AUTH_URL", None),
        "verify_ssl": getattr(settings, "GIGACHAT_VERIFY_SSL", True),
        "ca_bundle_file": getattr(settings, "GIGACHAT_CA_BUNDLE_FILE", None),
    }
    # Убираем None, чтобы PROVIDER_DEFAULTS фабрики могли их подставить.
    return LLMProviderFactory.create({k: v for k, v in config.items() if v is not None})


@lru_cache(maxsize=1)
def _get_prompt_registry() -> Any:
    """Вернуть общий PromptRegistry.

    Реестр читает YAML-шаблоны с диска и не имеет изменяемого состояния,
    поэтому кэшируется на процесс.
    """
    from app.infrastructure.llm.prompt_registry import PromptRegistry

    return PromptRegistry()


def _get_registry_provider() -> Any:
    """Вернуть провайдер реестра товарных знаков (Роспатент/ФИПС).

    Тип провайдера задаётся переменной окружения ``FIPS_PROVIDER``.
    Реальный провайдер использует официальный Open API поисковой платформы
    Роспатента и bearer API-ключ из настроек окружения.
    """
    from app.core.config import settings
    from app.infrastructure.providers.factory import ProviderFactory

    return ProviderFactory.create(
        {
            "provider": settings.FIPS_PROVIDER,
            "base_url": settings.FIPS_BASE_URL,
            "api_key": settings.FIPS_API_KEY,
            "trademark_datasets": settings.FIPS_TRADEMARK_DATASETS,
            "application_datasets": settings.FIPS_APPLICATION_DATASETS,
            "class_filter_field": settings.FIPS_CLASS_FILTER_FIELD,
            "timeout": settings.FIPS_TIMEOUT,
            "verify_ssl": settings.FIPS_VERIFY_SSL,
            "public_base_url": settings.FIPS_PUBLIC_BASE_URL,
            "public_data_sources": settings.FIPS_PUBLIC_DATA_SOURCES,
            "public_max_results": settings.FIPS_PUBLIC_MAX_RESULTS,
            "public_page_size": settings.FIPS_PUBLIC_PAGE_SIZE,
            "public_min_interval": settings.FIPS_PUBLIC_MIN_INTERVAL,
        }
    )


# Публичные псевдонимы — предпочтительны в новом коде.
get_llm_provider = _get_llm_provider
get_prompt_registry = _get_prompt_registry
get_registry_provider = _get_registry_provider

__all__ = [
    "_get_llm_provider",
    "_get_prompt_registry",
    "_get_registry_provider",
    "get_llm_provider",
    "get_prompt_registry",
    "get_registry_provider",
]
