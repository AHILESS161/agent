"""Детерминированное сравнение изображений обозначений.

Это лёгкий первый слой визуального поиска: он сравнивает уже найденные
текстовым/class-first поиском карточки и не пытается перебрать весь реестр.
Результат воспроизводим и не зависит от LLM.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.database.models import SourceDocument, TrademarkApplicationDraft
from app.services import file_storage

MAX_REGISTRY_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VISUAL_IMAGE_CHECKS = 16


@dataclass(frozen=True)
class VisualComparison:
    score: float
    difference_hash: float
    average_hash: float
    color_histogram: float
    aspect_ratio: float
    cache_key: str
    mime_type: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "difference_hash": round(self.difference_hash, 3),
            "average_hash": round(self.average_hash, 3),
            "color_histogram": round(self.color_histogram, 3),
            "aspect_ratio": round(self.aspect_ratio, 3),
            "cache_key": self.cache_key,
            "mime_type": self.mime_type,
            "method": "dhash+ahash+color_histogram+aspect_ratio",
        }


def _open(content: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(content))
        width, height = image.size
        if width < 1 or height < 1 or width * height > settings.OCR_MAX_IMAGE_PIXELS:
            raise ValueError("Некорректный размер изображения")
        image.load()
        return ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Ответ реестра не является изображением") from exc


def _hash_bits(image: Image.Image, *, difference: bool) -> list[int]:
    gray = image.convert("L")
    if difference:
        pixels = list(gray.resize((9, 8)).getdata())
        return [
            int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
            for row in range(8)
            for column in range(8)
        ]
    pixels = list(gray.resize((8, 8)).getdata())
    average = sum(pixels) / len(pixels)
    return [int(value >= average) for value in pixels]


def _bit_similarity(left: list[int], right: list[int]) -> float:
    return 1.0 - sum(a != b for a, b in zip(left, right, strict=True)) / len(left)


def _histogram(image: Image.Image) -> list[float]:
    resized = image.resize((128, 128))
    values: list[float] = []
    for channel in resized.split():
        raw = channel.histogram()
        bins = [sum(raw[index : index + 32]) for index in range(0, 256, 32)]
        total = float(sum(bins)) or 1.0
        values.extend(value / total for value in bins)
    return values


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def compare_images(left: bytes, right: bytes, *, cache_key: str, mime_type: str) -> VisualComparison:
    first = _open(left)
    second = _open(right)
    difference = _bit_similarity(
        _hash_bits(first, difference=True), _hash_bits(second, difference=True)
    )
    average = _bit_similarity(
        _hash_bits(first, difference=False), _hash_bits(second, difference=False)
    )
    histogram = max(0.0, min(1.0, _cosine(_histogram(first), _histogram(second))))
    first_ratio = first.width / first.height
    second_ratio = second.width / second.height
    aspect = min(first_ratio, second_ratio) / max(first_ratio, second_ratio)
    score = round(
        0.38 * difference + 0.32 * average + 0.22 * histogram + 0.08 * aspect,
        6,
    )
    return VisualComparison(score, difference, average, histogram, aspect, cache_key, mime_type)


def _cache_root() -> Path:
    root = file_storage.get_storage_root() / "registry-images"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def cache_registry_image(content: bytes, mime_type: str) -> str:
    extension = ".png" if mime_type == "image/png" else ".jpg"
    key = hashlib.sha256(content).hexdigest() + extension
    target = (_cache_root() / key).resolve()
    if not target.is_relative_to(_cache_root()):
        raise ValueError("Недопустимый путь кэша")
    if not target.exists():
        target.write_bytes(content)
    return key


def read_cached_registry_image(cache_key: str) -> bytes:
    target = (_cache_root() / Path(cache_key).name).resolve()
    if not target.is_relative_to(_cache_root()) or not target.exists():
        raise FileNotFoundError(cache_key)
    return target.read_bytes()


async def applicant_image(
    session: AsyncSession, application: TrademarkApplicationDraft
) -> bytes | None:
    raw_id = application.mark_image_file_id
    if not raw_id or not str(raw_id).isdigit():
        return None
    document = (
        await session.execute(
            select(SourceDocument).where(
                SourceDocument.id == int(raw_id),
                SourceDocument.application_id == application.id,
            )
        )
    ).scalar_one_or_none()
    if document is None:
        return None
    try:
        return file_storage.read_file(document.stored_path)
    except FileNotFoundError:
        return None


async def fetch_registry_image(provider: Any, image_url: str) -> tuple[bytes, str]:
    fetch = getattr(provider, "fetch_image", None)
    if callable(fetch):
        result = await fetch(image_url)
        if not isinstance(result, tuple) or len(result) != 2:
            raise ValueError("Провайдер вернул некорректное изображение")
        content, mime_type = result
    else:
        # Универсальный fallback разрешён только для доменов Роспатента.
        parsed = httpx.URL(image_url)
        host = (parsed.host or "").casefold()
        if parsed.scheme != "https" or not (
            host == "rospatent.gov.ru" or host.endswith(".rospatent.gov.ru")
        ):
            raise ValueError("Недоверенный адрес изображения реестра")
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(image_url, headers={"Accept": "image/*"})
            response.raise_for_status()
            content = response.content
            mime_type = response.headers.get("content-type", "").split(";", 1)[0]
    detected_mime = file_storage.detect_mime(content, "registry-image")
    if detected_mime not in {"image/png", "image/jpeg"}:
        raise ValueError("Реестр вернул неподдерживаемый формат изображения")
    if not content or len(content) > MAX_REGISTRY_IMAGE_BYTES:
        raise ValueError("Некорректный размер изображения реестра")
    _open(content)
    return content, detected_mime


async def compare_registry_candidates(
    applicant: bytes,
    candidates: list[Any],
    provider: Any,
    *,
    limit: int = MAX_VISUAL_IMAGE_CHECKS,
) -> tuple[dict[str, VisualComparison], list[str]]:
    selected = [record for record in candidates if getattr(record, "image_url", None)][:limit]
    semaphore = asyncio.Semaphore(4)

    async def process(record: Any) -> tuple[str, VisualComparison | None, str | None]:
        try:
            async with semaphore:
                content, mime_type = await fetch_registry_image(provider, record.image_url)
            cache_key = cache_registry_image(content, mime_type)
            comparison = compare_images(
                applicant, content, cache_key=cache_key, mime_type=mime_type
            )
            return record.record_id, comparison, None
        except (ValueError, OSError, httpx.HTTPError) as exc:
            return record.record_id, None, f"{record.record_id}: {exc}"

    results: dict[str, VisualComparison] = {}
    errors: list[str] = []
    for record_id, comparison, error in await asyncio.gather(
        *(process(record) for record in selected)
    ):
        if comparison is not None:
            results[record_id] = comparison
        if error:
            errors.append(error)
    return results, errors
