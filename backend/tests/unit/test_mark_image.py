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
