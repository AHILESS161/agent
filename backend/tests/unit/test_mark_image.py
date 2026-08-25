from __future__ import annotations

import io

from PIL import Image

from app.services import mark_image
from app.services.document_text_extractor import NoTextLayerError


def test_graphic_without_text_is_valid(monkeypatch):
    stream = io.BytesIO()
    Image.new("RGB", (64, 32), (255, 0, 0)).save(stream, format="PNG")
    monkeypatch.setattr(
        mark_image,
        "extract_pages_from_bytes",
        lambda *_: (_ for _ in ()).throw(NoTextLayerError("Текст не найден")),
    )

    result = mark_image.process_mark_image(stream.getvalue(), "logo.png")

    assert result.width == 64
    assert result.height == 32
    assert result.image_format == "PNG"
    assert result.recognized_text == ""
    assert result.ocr_warning == "Текст не найден"
    assert len(result.perceptual_hash) == 16


def test_white_canvas_does_not_hide_logo_colors():
    image = Image.new("RGB", (1000, 500), "white")
    for x in range(100, 350):
        for y in range(100, 400):
            image.putpixel((x, y), (4, 43, 86))
    for x in range(400, 650):
        for y in range(100, 400):
            image.putpixel((x, y), (220, 100, 10))
    for x in range(700, 900):
        for y in range(150, 350):
            image.putpixel((x, y), (95, 160, 45))

    colors = mark_image._dominant_colors(image)

    assert any(value.startswith("#04") for value in colors)
    assert any(value.startswith("#DC") for value in colors)
    assert any(value.startswith("#5F") for value in colors)
