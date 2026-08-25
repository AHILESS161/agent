import io

import pytest
from PIL import Image

from app.services.mark_description import (
    build_mark_description_prompt,
    normalize_mark_language,
    normalize_mark_description,
    prepare_vision_image,
)


def test_prompt_requires_actual_graphic_elements_and_colors():
    prompt = build_mark_description_prompt(
        mark_type="combined", known_text="Дружелюбный Сосед"
    )

    assert "каждый существенный графический элемент" in prompt
    assert "основные фактически видимые цвета" in prompt
    assert "Дружелюбный Сосед" in prompt


def test_normalizes_description_and_unique_colors():
    description, colors = normalize_mark_description(
        {
            "description": "Комбинированное обозначение содержит словесный элемент и несколько подробно описанных графических элементов, расположенных слева и справа.",
            "colors": ["Тёмно-синий", "оранжевый", "Тёмно-синий"],
        }
    )

    assert description.startswith("Комбинированное обозначение")
    assert colors == ["тёмно-синий", "оранжевый"]


def test_normalizes_green_and_language_fields():
    _, colors = normalize_mark_description(
        {
            "description": "Комбинированное обозначение содержит словесный элемент и конкретно описанные графические элементы, расположенные в единой композиции.",
            "colors": ["Оранжевый", "тёмно-зелёный", "тёмно-синий"],
        }
    )
    transliteration, translation = normalize_mark_language(
        {
            "transliteration": "  DRUZHELYUBNYY   SOSED ",
            "translation": " Friendly Neighbor ",
        }
    )

    assert colors == ["оранжевый", "зеленый", "тёмно-синий"]
    assert transliteration == "DRUZHELYUBNYY SOSED"
    assert translation == "Friendly Neighbor"


def test_rejects_empty_generic_model_answer():
    with pytest.raises(ValueError, match="содержательное описание"):
        normalize_mark_description({"description": "Элементы на изображении.", "colors": []})


def test_prepares_small_rgb_jpeg_without_changing_original():
    source = io.BytesIO()
    Image.new("RGBA", (2400, 1200), (10, 40, 90, 180)).save(source, "PNG")

    prepared, mime = prepare_vision_image(source.getvalue())

    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(prepared)) as result:
        assert result.mode == "RGB"
        assert max(result.size) <= 1600
