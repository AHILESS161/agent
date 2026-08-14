"""Read-only access to trademark registrations and published applications."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_registry_provider
from app.core.config import settings
from app.core.security import require_roles
from app.infrastructure.database.models import User
from app.infrastructure.providers.base import RegistryRecord, SearchQuery
from app.infrastructure.providers.rospatent import RospatentConfigurationError

router = APIRouter(prefix="/registry", tags=["registry"])


class RegistrySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    classes: list[int] = Field(default_factory=list)
    search_type: Literal["exact", "fuzzy", "phonetic", "transliteration", "semantic"] = (
        "fuzzy"
    )
    source: Literal["registrations", "applications", "both"] = "both"
    max_results: int = Field(default=50, ge=1, le=200)


class RegistrySearchResponse(BaseModel):
    provider: str
    source: str
    total: int
    records: list[RegistryRecord]


class RegistryDatasetsResponse(BaseModel):
    provider: str
    datasets: list[dict[str, Any]]


def _raise_external_error(exc: Exception) -> None:
    if isinstance(exc, RospatentConfigurationError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in {401, 403}:
            detail = "Ключ Open API Роспатента отсутствует, истёк или не имеет доступа."
        elif code == 429:
            detail = "Роспатент временно ограничил частоту запросов."
        else:
            detail = f"Open API Роспатента вернул ошибку HTTP {code}."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Open API Роспатента временно недоступен.",
        )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Не удалось обработать ответ Open API Роспатента.",
    )


@router.post("/search", response_model=RegistrySearchResponse)
async def search_registry(
    payload: RegistrySearchRequest,
    _current_user: User = Depends(require_roles("admin", "lawyer", "manager")),
    provider: Any = Depends(get_registry_provider),
) -> RegistrySearchResponse:
    """Search registered marks, applications, or both data collections."""
    query = SearchQuery(
        mark_text=payload.query,
        classes=payload.classes or None,
        search_type=payload.search_type,
        max_results=payload.max_results,
    )
    try:
        if payload.source == "registrations":
            groups = [await provider.search_marks(query)]
        elif payload.source == "applications":
            groups = [await provider.search_applications(query)]
        else:
            groups = list(
                await asyncio.gather(
                    provider.search_marks(query), provider.search_applications(query)
                )
            )
    except Exception as exc:  # noqa: BLE001
        _raise_external_error(exc)
        raise AssertionError("unreachable")

    records: dict[str, RegistryRecord] = {}
    if payload.source == "both":
        # Preserve visibility of both stages when a small global limit is used.
        # Concatenating groups would let registrations consume the whole limit
        # before the first published application is added.
        for index in range(max((len(group) for group in groups), default=0)):
            for group in groups:
                if index < len(group):
                    record = group[index]
                    records.setdefault(record.record_id, record)
                    if len(records) >= payload.max_results:
                        break
            if len(records) >= payload.max_results:
                break
    else:
        for group in groups:
            for record in group:
                records.setdefault(record.record_id, record)
    result = list(records.values())[: payload.max_results]
    return RegistrySearchResponse(
        provider=settings.FIPS_PROVIDER,
        source=payload.source,
        total=len(result),
        records=result,
    )


@router.get("/datasets", response_model=RegistryDatasetsResponse)
async def list_registry_datasets(
    _current_user: User = Depends(require_roles("admin", "lawyer")),
    provider: Any = Depends(get_registry_provider),
) -> RegistryDatasetsResponse:
    """Return official Search Platform datasets available to the configured key."""
    if not hasattr(provider, "list_datasets"):
        return RegistryDatasetsResponse(provider=settings.FIPS_PROVIDER, datasets=[])
    try:
        datasets = await provider.list_datasets()
    except Exception as exc:  # noqa: BLE001
        _raise_external_error(exc)
        raise AssertionError("unreachable")
    return RegistryDatasetsResponse(provider=settings.FIPS_PROVIDER, datasets=datasets)


@router.get("/records/{record_id}", response_model=RegistryRecord)
async def get_registry_record(
    record_id: str,
    _current_user: User = Depends(require_roles("admin", "lawyer", "manager")),
    provider: Any = Depends(get_registry_provider),
) -> RegistryRecord:
    """Load a full registry card by the identifier returned by search."""
    try:
        record = await provider.get_record(record_id)
    except Exception as exc:  # noqa: BLE001
        _raise_external_error(exc)
        raise AssertionError("unreachable")
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    return record
