from __future__ import annotations

import io

from PIL import Image, ImageDraw

from app.services.visual_mark_similarity import compare_images


def _image(*, inverted: bool = False) -> bytes:
    stream = io.BytesIO()
    image = Image.new("RGB", (160, 100), "white" if not inverted else "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((15, 20, 75, 80), fill="black" if not inverted else "white")
    draw.ellipse((95, 20, 145, 75), fill="#0c9e9a")
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_identical_logo_has_maximum_visual_score():
    content = _image()
    result = compare_images(
        content, content, cache_key="same.png", mime_type="image/png"
    )
    assert result.score == 1.0
    assert result.difference_hash == 1.0
    assert result.color_histogram == 1.0


def test_different_composition_scores_lower():
    result = compare_images(
        _image(), _image(inverted=True), cache_key="other.png", mime_type="image/png"
    )
    assert 0 <= result.score < 0.9
