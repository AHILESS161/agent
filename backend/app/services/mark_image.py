"""Безопасная подготовка изображения товарного знака.

Модуль не делает юридический вывод о визуальном сходстве. Он проверяет,
что файл действительно является изображением, извлекает воспроизводимые
технические признаки и пытается распознать словесные элементы для
последующего подтверждения человеком.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.services.document_text_extractor import (
    NoTextLayerError,
    UnsupportedDocumentType,
    extract_pages_from_bytes,
)


class MarkImageError(ValueError):
    """Изображение обозначения не прошло проверку."""


@dataclass(frozen=True)
class MarkImageResult:
    width: int
    height: int
    image_format: str
    color_mode: str
    dominant_colors: list[str]
    perceptual_hash: str
    recognized_text: str
    ocr_confidence: float | None
    ocr_warning: str | None

    def metadata(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "format": self.image_format,
            "color_mode": self.color_mode,
            "dominant_colors": self.dominant_colors,
            "perceptual_hash": self.perceptual_hash,
            "ocr_warning": self.ocr_warning,
        }


def _dominant_colors(image: Image.Image, count: int = 8) -> list[str]:
    rgb = ImageOps.exif_transpose(image).convert("RGB")
    rgb.thumbnail((192, 192))
    # У логотипов часто огромный белый холст. Если квантизовать его вместе с
    # рисунком, вся палитра заполняется почти белыми оттенками и реальные цвета
    # (синий, оранжевый, зелёный) теряются.
    foreground = [
        pixel
        for pixel in rgb.getdata()
        if not (
            min(pixel) >= 235
            or (max(pixel) - min(pixel) <= 14 and sum(pixel) / 3 >= 210)
        )
    ]
    if not foreground:
        foreground = list(rgb.getdata())
    sample = Image.new("RGB", (len(foreground), 1))
    sample.putdata(foreground)
    quantized = sample.quantize(colors=min(count, len(set(foreground))))
    palette = quantized.getpalette() or []
    colors = sorted(quantized.getcolors() or [], reverse=True)
    result: list[str] = []
    for _, index in colors[:count]:
        offset = index * 3
        if offset + 2 >= len(palette):
            continue
        red, green, blue = palette[offset : offset + 3]
        result.append(f"#{red:02X}{green:02X}{blue:02X}")
    return result


def _difference_hash(image: Image.Image) -> str:
    """64-битный dHash для дедупликации и будущего визуального индекса."""
    gray = ImageOps.exif_transpose(image).convert("L").resize((9, 8))
    pixels = list(gray.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | int(
                pixels[row * 9 + column] > pixels[row * 9 + column + 1]
            )
    return f"{value:016x}"


def process_mark_image(content: bytes, filename: str) -> MarkImageResult:
    try:
        with Image.open(io.BytesIO(content)) as source:
            image_format = (source.format or "").upper()
            if image_format not in {"PNG", "JPEG"}:
                raise MarkImageError("Для обозначения поддерживаются только PNG и JPEG")
            width, height = source.size
            if width < 1 or height < 1:
                raise MarkImageError("У изображения некорректный размер")
            pixels = width * height
            if pixels > settings.OCR_MAX_IMAGE_PIXELS:
                raise MarkImageError(
                    "Изображение слишком большое: максимум "
                    f"{settings.OCR_MAX_IMAGE_PIXELS:,} пикселей"
                )
            source.load()
            color_mode = source.mode
            dominant_colors = _dominant_colors(source)
            perceptual_hash = _difference_hash(source)
    except MarkImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MarkImageError("Не удалось открыть изображение: файл повреждён") from exc

    recognized_text = ""
    confidence: float | None = None
    warning: str | None = None
    try:
        pages = extract_pages_from_bytes(content, filename)
        recognized_text = "\n".join(page.text.strip() for page in pages if page.text.strip())
        confidences = [
            page.ocr_confidence for page in pages if page.ocr_confidence is not None
        ]
        confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
    except (NoTextLayerError, UnsupportedDocumentType) as exc:
        # Для чисто графического знака отсутствие текста — нормальный результат.
        warning = str(exc)

    return MarkImageResult(
        width=width,
        height=height,
        image_format=image_format,
        color_mode=color_mode,
        dominant_colors=dominant_colors,
        perceptual_hash=perceptual_hash,
        recognized_text=recognized_text,
        ocr_confidence=confidence,
        ocr_warning=warning,
    )
