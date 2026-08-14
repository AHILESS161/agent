"""Client for the official Rospatent Search Platform Open API.

Official API documentation (ИС «Поисковая платформа») describes:

* ``POST /search`` for full-text and natural-language search;
* ``GET /datasets`` for available search collections;
* ``GET /docs/{id}`` for a document card;
* bearer JWT/API keys generated in the Search Platform user interface.

The public response schema has evolved since the published 2022 document and
trademark collections contain fields absent from the old patent-only example.
The normaliser below intentionally accepts both the documented common/biblio
shape and the current flat trademark-card shape.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Iterable
from urllib.parse import quote

import httpx

from app.infrastructure.providers.base import (
    ExternalStatusResult,
    RegistryRecord,
    SearchQuery,
    SubmissionPayload,
    SubmissionResult,
)


class RospatentConfigurationError(ValueError):
    """The real provider cannot run with the supplied configuration."""


def _path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _first(data: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value = _path(data, path)
        if value not in (None, "", [], {}):
            return value
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"<[^>]+>", "", value).strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [_as_text(item) for item in value]
        return "; ".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in (
            "name",
            "title",
            "value",
            "text",
            "fullname",
            "full_name",
            "designation",
        ):
            if value.get(key) not in (None, ""):
                return _as_text(value[key])
    return ""


def _parse_classes(value: Any) -> list[int]:
    values: list[Any]
    if isinstance(value, list):
        values = value
    elif value in (None, ""):
        values = []
    else:
        values = [value]

    result: set[int] = set()
    for item in values:
        if isinstance(item, dict):
            item = _first(
                item,
                "class_number",
                "nice_class",
                "class",
                "number",
                "code",
                "name",
                "fullname",
            )
        for match in re.findall(
            r"(?<!\d)(?:0?[1-9]|[1-3]\d|4[0-5])(?!\d)",
            str(item or ""),
        ):
            result.add(int(match))
    return sorted(result)


def _normalise_date(value: Any) -> str | None:
    text = _as_text(value)
    if not text:
        return None
    compact = re.sub(r"\D", "", text)
    if len(compact) == 8 and compact[:4].isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return text


def _normalise_status(value: Any, source: str) -> str:
    status = _as_text(value).casefold()
    if source == "application" and not status:
        return "pending"
    if any(word in status for word in ("действ", "valid", "active", "registered")):
        return "registered"
    if any(
        word in status
        for word in (
            "заяв",
            "pending",
            "received",
            "processing",
            "examination",
            "рассмотр",
            "экспертиз",
        )
    ):
        return "pending"
    if any(word in status for word in ("истек", "expired", "termination")):
        return "expired"
    if any(
        word in status
        for word in ("отозв", "отклон", "прекращ", "аннулир", "cancel", "reject", "invalid")
    ):
        return "cancelled"
    return "pending" if source == "application" else "registered"


def _normalise_mark_type(value: Any) -> str:
    text = _as_text(value).casefold()
    if any(word in text for word in ("word", "словес")):
        return "word"
    if any(word in text for word in ("figurative", "изобраз")):
        return "figurative"
    if any(word in text for word in ("combined", "комбинир")):
        return "combined"
    if any(word in text for word in ("three", "объем", "объём")):
        return "three_dimensional"
    return text or "unknown"


def _unwrap_hit(hit: Any) -> dict[str, Any]:
    if not isinstance(hit, dict):
        return {}
    source = hit.get("_source")
    if isinstance(source, dict):
        return {**hit, **source}
    document = hit.get("document")
    if isinstance(document, dict):
        return {**hit, **document}
    return hit


def _record_from_document(document: dict[str, Any], source: str) -> RegistryRecord:
    data = _unwrap_hit(document)
    application_number = _as_text(
        _first(
            data,
            "application_number",
            "application.number",
            "common.application.number",
            "trademark.application_number",
        )
    ) or None
    registration_number = _as_text(
        _first(
            data,
            "certificate_number",
            "registration_number",
            "reg_number",
            "common.document_number",
            "trademark.certificate_number",
        )
    ) or None
    raw_id = _as_text(
        _first(data, "id", "_id", "identity", "common.identity", "document_id")
    ) or registration_number or application_number
    if not raw_id:
        raise ValueError("Rospatent document has no identifier")

    mark_text = _as_text(
        _first(
            data,
            "mark_text",
            "name",
            "designation",
            "trademark.name",
            "biblio.ru.title",
            "biblio.ru.name",
            "biblio.en.title",
            "common.title",
        )
    )
    owner = _as_text(
        _first(
            data,
            "owner",
            "copyright_holder",
            "right_holder",
            "rightholder",
            "applicants",
            "applicant",
            "biblio.ru.applicant",
            "biblio.ru.patentee",
            "biblio.en.applicant",
        )
    )
    classes = _parse_classes(
        _first(
            data,
            "classes",
            "icgs",
            "nice_classes",
            "classification.icgs",
            "common.classification.icgs",
            "trademark.icgs",
        )
    )
    image_url = _as_text(
        _first(data, "image_url", "image.url", "image", "trademark.image_url")
    ) or None
    status_value = _first(data, "status", "state", "legal_status", "common.status")

    return RegistryRecord(
        record_id=f"rospatent:{source}:{raw_id}",
        external_id=raw_id,
        source=source,
        mark_text=mark_text,
        mark_type=_normalise_mark_type(
            _first(data, "mark_type", "trademark_type", "type", "trademark.type")
        ),
        owner=owner,
        classes=classes,
        status=_normalise_status(status_value, source),
        filing_date=_normalise_date(
            _first(
                data,
                "filing_date",
                "application_date",
                "publication_date",
                "application.filing_date",
                "common.application.filing_date",
            )
        ),
        registration_date=_normalise_date(
            _first(data, "registration_date", "common.registration_date")
        ),
        application_number=application_number,
        registration_number=registration_number,
        image_url=image_url,
    )


def _iter_datasets(items: Iterable[Any]) -> Iterable[dict[str, Any]]:
    for item in items:
        if not isinstance(item, dict):
            continue
        yield item
        children = item.get("children") or item.get("datasets") or []
        if isinstance(children, list):
            yield from _iter_datasets(children)


class RospatentSearchProvider:
    """Trademark registry provider backed by the official Search Platform."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://searchplatform.rospatent.gov.ru/patsearch/v0.2/",
        trademark_datasets: list[str] | None = None,
        application_datasets: list[str] | None = None,
        class_filter_field: str = "classification.icgs",
        timeout: float = 30.0,
        verify_ssl: bool = True,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise RospatentConfigurationError(
                "FIPS_API_KEY is required for the Rospatent Search Platform"
            )
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/") + "/"
        self.trademark_datasets = list(trademark_datasets or [])
        self.application_datasets = list(application_datasets or [])
        self.class_filter_field = class_filter_field
        self.timeout = timeout
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            verify=verify_ssl,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        self._owns_client = client is None
        self._datasets_lock = asyncio.Lock()
        self._datasets_loaded = False

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        retryable = {429, 500, 502, 503, 504}
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **kwargs.pop("headers", {}),
        }
        for attempt in range(3):
            try:
                response = await self._client.request(
                    method, path.lstrip("/"), headers=headers, **kwargs
                )
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            if response.status_code in retryable and attempt < 2:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("Rospatent request failed after retries")

    async def list_datasets(self) -> list[dict[str, Any]]:
        payload = (await self._request("GET", "datasets")).json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("datasets", "results", "items"):
                if isinstance(payload.get(key), list):
                    return payload[key]
        raise ValueError("Unexpected Rospatent datasets response")

    async def _ensure_datasets(self, source: str) -> None:
        configured = (
            self.trademark_datasets
            if source == "registration"
            else self.application_datasets
        )
        if configured:
            return
        async with self._datasets_lock:
            if not self._datasets_loaded:
                datasets = await self.list_datasets()
                registrations: list[str] = []
                applications: list[str] = []
                generic: list[str] = []
                for item in _iter_datasets(datasets):
                    identifier = _as_text(
                        _first(
                            item,
                            "id",
                            "_id",
                            "code",
                            "value",
                            "dataset",
                            "identifier",
                        )
                    )
                    name = " ".join(
                        _as_text(item.get(key))
                        for key in (
                            "name_ru",
                            "name_en",
                            "name",
                            "title",
                            "description",
                        )
                    ).casefold()
                    if not identifier or not any(
                        token in name
                        for token in ("товарн", "trademark", "service mark")
                    ):
                        continue
                    if any(token in name for token in ("заяв", "application")):
                        applications.append(identifier)
                    elif any(
                        token in name
                        for token in (
                            "регист",
                            "свидетель",
                            "registered",
                            "certificate",
                        )
                    ):
                        registrations.append(identifier)
                    else:
                        # В актуальном интерфейсе встречается единый набор
                        # «Товарные знаки», содержащий карточки на разных стадиях.
                        generic.append(identifier)
                if not self.trademark_datasets:
                    self.trademark_datasets = list(
                        dict.fromkeys(registrations or generic)
                    )
                if not self.application_datasets:
                    self.application_datasets = list(
                        dict.fromkeys(applications or generic)
                    )
                self._datasets_loaded = True

        selected = (
            self.trademark_datasets
            if source == "registration"
            else self.application_datasets
        )
        if not selected:
            raise RospatentConfigurationError(
                f"Rospatent dataset for {source} records was not discovered. "
                "Set FIPS_TRADEMARK_DATASETS or FIPS_APPLICATION_DATASETS "
                "from GET /datasets."
            )

    def _search_payload(self, query: SearchQuery, datasets: list[str]) -> dict[str, Any]:
        text = query.mark_text.strip()
        payload: dict[str, Any] = {
            "limit": min(max(query.max_results, 1), 200),
            "offset": 0,
            "datasets": datasets,
            "sort": "relevance",
        }
        if query.search_type == "exact":
            escaped = text.replace('"', '\\"')
            payload["q"] = f'"{escaped}"'
        elif query.search_type == "fuzzy":
            payload["q"] = f"{text}~2"
        else:
            payload["qn"] = text
        if query.classes:
            values = list(
                dict.fromkeys(
                    [str(number) for number in query.classes]
                    + [f"{number:02d}" for number in query.classes]
                )
            )
            payload["filter"] = {self.class_filter_field: {"values": values}}
        return payload

    async def _search(self, query: SearchQuery, source: str) -> list[RegistryRecord]:
        await self._ensure_datasets(source)
        datasets = self.trademark_datasets if source == "registration" else self.application_datasets
        response = await self._request(
            "POST", "search", json=self._search_payload(query, datasets)
        )
        payload = response.json()
        hits: Any = payload.get("hits", []) if isinstance(payload, dict) else []
        if isinstance(hits, dict):
            hits = hits.get("hits", [])
        if not isinstance(hits, list):
            raise ValueError("Unexpected Rospatent search response")

        records: list[RegistryRecord] = []
        for hit in hits:
            try:
                record = _record_from_document(hit, source)
            except (TypeError, ValueError):
                continue
            if query.classes and record.classes and not set(query.classes) & set(record.classes):
                continue
            records.append(record)
        return records[: query.max_results]

    async def search_marks(self, query: SearchQuery) -> list[RegistryRecord]:
        return await self._search(query, "registration")

    async def search_applications(self, query: SearchQuery) -> list[RegistryRecord]:
        return await self._search(query, "application")

    async def get_record(self, record_id: str) -> RegistryRecord | None:
        parts = record_id.split(":", 2)
        source = parts[1] if len(parts) == 3 else "registration"
        external_id = parts[2] if len(parts) == 3 else record_id
        try:
            response = await self._request("GET", f"docs/{quote(external_id, safe='')}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return _record_from_document(response.json(), source)

    async def submit_application(self, payload: SubmissionPayload) -> SubmissionResult:
        del payload
        return SubmissionResult(
            success=False,
            external_id=None,
            error_message=(
                "The Search Platform API is read-only for this integration. "
                "Submission uses the separate Online Rospatent external_api and is disabled."
            ),
        )

    async def get_status(self, external_submission_id: str) -> ExternalStatusResult:
        raise NotImplementedError(
            "Application status belongs to the separate Online Rospatent external_api"
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
