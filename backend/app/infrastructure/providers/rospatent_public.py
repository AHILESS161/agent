"""Read-only adapter for the public Rospatent trademark search page.

The page at ``https://searchplatform.rospatent.gov.ru/trademarks`` uses an
anonymous Socket.IO namespace to send search jobs to the internal
``esi-search`` service.  This is not the documented Open API: the protocol can
change without notice and the result must be presented as a preliminary,
limited search.

The adapter deliberately uses Engine.IO HTTP long-polling rather than browser
automation or HTML scraping.  It performs only the same read-only search that
is available to an anonymous visitor, applies conservative request limits and
does not attempt to bypass authentication or access controls.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from app.infrastructure.providers.base import (
    ExternalStatusResult,
    RegistryRecord,
    SearchQuery,
    SubmissionPayload,
    SubmissionResult,
)
from app.infrastructure.providers.rospatent import _as_text, _parse_classes

_ENGINE_SEPARATOR = "\x1e"
_NAMESPACE = "/search"
_EVENT_PREFIX = f"42{_NAMESPACE},"


class RospatentPublicProtocolError(RuntimeError):
    """The undocumented public protocol returned an unexpected response."""


def _date(value: Any) -> str | None:
    text = _as_text(value)
    if not text or text.startswith("0001-01-01"):
        return None
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return text


def _source_of(item: dict[str, Any]) -> str:
    kind = _as_text(item.get("tmk_kind")).casefold()
    numeric_kind = str(item.get("trademarkKind") or "")
    if numeric_kind == "2" or any(word in kind for word in ("заяв", "application")):
        return "application"
    if not item.get("reg_number") and item.get("appl_number"):
        return "application"
    return "registration"


def _status_of(item: dict[str, Any], source: str) -> str:
    if source == "application":
        return "pending"
    code = str(item.get("status_code") or "")
    if code == "1":
        return "cancelled"
    if code == "2":
        return "registered"
    expiry = _date(item.get("expiry_date"))
    if expiry and expiry < time.strftime("%Y-%m-%d"):
        return "expired"
    return "registered"


def _image_url(item: dict[str, Any]) -> str | None:
    files = item.get("files")
    if isinstance(files, list):
        for file in files:
            if isinstance(file, dict) and file.get("file_url"):
                return _as_text(file["file_url"]) or None
    variants = item.get("variant_files")
    if isinstance(variants, dict):
        for group in variants.values():
            if isinstance(group, list):
                for file in group:
                    if isinstance(file, dict) and file.get("file_url"):
                        return _as_text(file["file_url"]) or None
    return None


def _record_from_public_result(item: dict[str, Any]) -> RegistryRecord:
    source = _source_of(item)
    external_id = _as_text(
        item.get("object_uid")
        or item.get("ois_uid")
        or item.get("reg_number")
        or item.get("appl_number")
    )
    if not external_id:
        raise ValueError("Public Rospatent result has no identifier")

    mark_text = _as_text(
        item.get("mark_description_text")
        or item.get("appl_description_text")
        or item.get("name")
    )
    classes = _parse_classes(
        item.get("goodClasses") or item.get("goods_classes") or item.get("goods")
    )
    application_number = _as_text(item.get("appl_number")) or None
    registration_number = _as_text(item.get("reg_number")) or None

    return RegistryRecord(
        record_id=f"rospatent-public:{source}:{external_id}",
        external_id=external_id,
        source=source,
        mark_text=mark_text,
        mark_type="word" if mark_text else "figurative",
        owner=_as_text(item.get("holders") or item.get("applicants")),
        classes=classes,
        status=_status_of(item, source),
        filing_date=_date(item.get("appl_date")),
        registration_date=_date(item.get("reg_date")),
        application_number=application_number,
        registration_number=registration_number,
        image_url=_image_url(item),
    )


def _event_from_packet(packet: str) -> tuple[str, Any] | None:
    if not packet.startswith(_EVENT_PREFIX):
        return None
    try:
        value = json.loads(packet[len(_EVENT_PREFIX) :])
    except json.JSONDecodeError as exc:
        raise RospatentPublicProtocolError("Invalid Socket.IO event JSON") from exc
    if not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], str):
        raise RospatentPublicProtocolError("Invalid Socket.IO event structure")
    return value[0], value[1]


class RospatentPublicSearchProvider:
    """Limited provider backed by the anonymous public trademark search UI."""

    def __init__(
        self,
        base_url: str = "https://searchplatform.rospatent.gov.ru/",
        data_sources: list[str] | None = None,
        timeout: float = 30.0,
        verify_ssl: bool = True,
        max_results: int = 100,
        page_size: int = 50,
        min_interval: float = 0.75,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.data_sources = list(
            data_sources
            or ["trademarks", "known_trademarks", "international_trademarks"]
        )
        self.timeout = max(5.0, timeout)
        self.max_results = min(max(max_results, 1), 200)
        self.page_size = min(max(page_size, 1), 100)
        self.min_interval = max(0.0, min_interval)
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            verify=verify_ssl,
            headers={
                "Accept": "*/*",
                "User-Agent": "TrademarkSystem/0.1 (public Rospatent search)",
            },
        )
        self._owns_client = client is None
        self._rate_lock = asyncio.Lock()
        self._last_task_at = 0.0
        self._record_cache: dict[str, RegistryRecord] = {}

    async def _request(self, method: str, **kwargs: Any) -> httpx.Response:
        retryable = {429, 500, 502, 503, 504}
        for attempt in range(3):
            try:
                response = await self._client.request(method, "socket.io/", **kwargs)
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
        raise RospatentPublicProtocolError("Public Rospatent request failed")

    @staticmethod
    def _params(sid: str | None = None) -> dict[str, str]:
        params = {
            "EIO": "4",
            "transport": "polling",
            "t": str(time.time_ns()),
        }
        if sid:
            params["sid"] = sid
        return params

    async def _post_packet(self, sid: str, packet: str) -> None:
        await self._request(
            "POST",
            params=self._params(sid),
            content=packet.encode("utf-8"),
            headers={"Content-Type": "text/plain;charset=UTF-8"},
        )

    async def _poll(self, sid: str) -> list[str]:
        response = await self._request("GET", params=self._params(sid))
        return [packet for packet in response.text.split(_ENGINE_SEPARATOR) if packet]

    async def _connect(self) -> str:
        response = await self._request("GET", params=self._params())
        packet = response.text
        if not packet.startswith("0"):
            raise RospatentPublicProtocolError("Engine.IO handshake was not returned")
        try:
            handshake = json.loads(packet[1:])
            sid = str(handshake["sid"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RospatentPublicProtocolError("Invalid Engine.IO handshake") from exc

        await self._post_packet(sid, f"40{_NAMESPACE},")
        packets = await self._poll(sid)
        if not any(packet.startswith(f"40{_NAMESPACE}") for packet in packets):
            raise RospatentPublicProtocolError("Socket.IO namespace was not opened")
        return sid

    async def _throttle(self) -> None:
        async with self._rate_lock:
            delay = self.min_interval - (time.monotonic() - self._last_task_at)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_task_at = time.monotonic()

    def _task(
        self,
        query: SearchQuery,
        page: int,
        size: int,
        source: str,
    ) -> dict[str, Any]:
        parameters = {
            "algorithm_id": 1,
            "search_kind_id": "match" if query.search_type == "exact" else "fuzzy",
            "join_words": True,
            "use_edge_ngram": False,
            "use_reversed_edge_ngram": False,
            "split": False,
            "algorithm_val": 2,
            "data_sources": self.data_sources,
            "similar_letter": False,
            "morphological": False,
            "stopwords": True,
            "translate": False,
            "transliteration": False,
            "languages": [],
        }
        filters: dict[str, Any] = {}
        if query.classes:
            filters["goods_classes"] = [f"{number:02d}" for number in query.classes]
        if source == "application":
            filters["trademark_type"] = 2
        return {
            "method": "POST",
            "service_name": "esi-search",
            "service_path": "/api/v1/search",
            "params": {"page": page, "size": size},
            "data": {
                "query": {
                    "data": {
                        "search_query": query.mark_text.strip(),
                        "parameters": parameters,
                    },
                    "type": "search_letter",
                },
                "filter": filters,
                "info": "",
                "oisType": "trademarks",
            },
        }

    async def _run_task(self, task: dict[str, Any]) -> dict[str, Any]:
        await self._throttle()
        sid: str | None = None
        try:
            sid = await self._connect()
            event = _EVENT_PREFIX + json.dumps(
                ["send_task", task], ensure_ascii=False, separators=(",", ":")
            )
            await self._post_packet(sid, event)
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                for packet in await self._poll(sid):
                    if packet == "2":
                        await self._post_packet(sid, "3")
                        continue
                    decoded = _event_from_packet(packet)
                    if decoded is None:
                        continue
                    name, payload = decoded
                    if name == "send_results":
                        if not isinstance(payload, dict):
                            raise RospatentPublicProtocolError(
                                "Search result is not an object"
                            )
                        return payload
                    if name in {"send_error", "error"}:
                        raise RospatentPublicProtocolError(_as_text(payload))
            raise httpx.TimeoutException("Public Rospatent search timed out")
        finally:
            if sid:
                try:
                    await self._post_packet(sid, f"41{_NAMESPACE},")
                except (httpx.HTTPError, RospatentPublicProtocolError):
                    pass

    async def _search(self, query: SearchQuery, source: str) -> list[RegistryRecord]:
        if not query.mark_text.strip():
            return []
        target = min(query.max_results, self.max_results)
        # Registration results include domestic, well-known and international
        # marks. Overfetch because application cards are removed client-side.
        requested = min(
            self.max_results,
            max(target, target * 2 if source == "registration" else target),
        )
        records: dict[str, RegistryRecord] = {}
        page = 1
        total_pages = 1
        while len(records) < target and page <= total_pages:
            size = min(self.page_size, requested)
            payload = await self._run_task(self._task(query, page, size, source))
            total_pages = max(1, int(payload.get("totalPages") or 1))
            items = payload.get("data") or []
            if not isinstance(items, list):
                raise RospatentPublicProtocolError("Search data is not a list")
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    record = _record_from_public_result(item)
                except ValueError:
                    continue
                if record.source != source:
                    continue
                if query.classes and record.classes:
                    if not set(query.classes) & set(record.classes):
                        continue
                records.setdefault(record.record_id, record)
                self._record_cache[record.record_id] = record
                if len(records) >= target:
                    break
            if not items or page * size >= requested:
                break
            page += 1
        return list(records.values())[:target]

    async def search_marks(self, query: SearchQuery) -> list[RegistryRecord]:
        return await self._search(query, "registration")

    async def search_applications(self, query: SearchQuery) -> list[RegistryRecord]:
        return await self._search(query, "application")

    async def list_datasets(self) -> list[dict[str, Any]]:
        labels = {
            "trademarks": "Товарные знаки РФ",
            "known_trademarks": "Общеизвестные товарные знаки РФ",
            "international_trademarks": "Международные товарные знаки",
        }
        return [
            {"id": source, "name_ru": labels.get(source, source), "public_ui": True}
            for source in self.data_sources
        ]

    async def get_record(self, record_id: str) -> RegistryRecord | None:
        return self._record_cache.get(record_id)

    async def submit_application(self, payload: SubmissionPayload) -> SubmissionResult:
        del payload
        return SubmissionResult(
            success=False,
            external_id=None,
            error_message="Public Rospatent search is read-only.",
        )

    async def get_status(self, external_submission_id: str) -> ExternalStatusResult:
        del external_submission_id
        raise NotImplementedError("Public Rospatent search has no submission status API")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
