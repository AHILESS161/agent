"""Подготовка проверяемого человеком описания графического обозначения."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageOps


DESCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "colors": {"type": "array", "items": {"type": "string"}},
        "transliteration": {"type": "string"},
        "translation": {"type": "string"},
    },
    "required": ["description", "colors", "transliteration", "translation"],
}


def prepare_vision_image(content: bytes) -> tuple[bytes, str]:
    """Уменьшить изображение для vision-запроса, не меняя оригинал в деле."""
    with Image.open(io.BytesIO(content)) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        background = Image.new("RGBA", image.size, "white")
        background.alpha_composite(image)
        rgb = background.convert("RGB")
        rgb.thumbnail((1600, 1600))
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=88, optimize=True)
        return buffer.getvalue(), "image/jpeg"


def build_mark_description_prompt(*, mark_type: str, known_text: str) -> str:
    text_hint = known_text.strip() or "не задан"
    return f"""
Подготовь проект описания изображения для заявки на товарный знак в Роспатенте.
Вид обозначения: {mark_type}. Предварительно распознанный словесный элемент: {text_hint}.

Опиши только то, что действительно видно на изображении:
1) точный словесный элемент и алфавит;
2) каждый существенный графический элемент, а не только общую фразу о графике;
3) их взаимное расположение и композицию;
4) основные фактически видимые цвета обычными русскими названиями;
5) читаемую транслитерацию словесного элемента латиницей;
6) перевод словесного элемента, если у слов есть обычное словарное значение.

Пиши одним связным абзацем из 3–5 предложений, нейтральным деловым языком,
ориентировочно 300–700 знаков. Начни с вида обозначения и точного словесного
элемента, затем опиши композицию и конкретные предметы на изображении.
Не описывай назначение бизнеса, эмоции, рекламный смысл, юридические свойства и сходство с другими знаками.
Не используй пустые формулы вроде «элементы приведены на изображении» вместо перечисления элементов.
В colors верни уникальные основные цвета без оттенков, которых нельзя уверенно различить.
Не называй зелёный тёмно-зелёным только из-за теней или сглаживания.
В transliteration верни только написание латиницей без пояснений.
В translation верни только перевод без пояснений; если перевод невозможен — пустую строку.
Пример: «Дружелюбный Сосед» → transliteration «DRUZHELYUBNYY SOSED», translation «Friendly Neighbor».
""".strip()


def normalize_mark_description(result: dict[str, Any]) -> tuple[str, list[str]]:
    description = " ".join(str(result.get("description") or "").split()).strip()
    if len(description) < 80:
        raise ValueError("Модель не подготовила содержательное описание изображения")
    colors: list[str] = []
    raw_colors = result.get("colors")
    if isinstance(raw_colors, list):
        for item in raw_colors:
            value = " ".join(str(item).split()).strip().lower().replace("ё", "е")
            value = {
                "темно-зеленый": "зеленый",
                "салатовый": "зеленый",
                "темно-синий": "тёмно-синий",
                "темно-голубой": "синий",
            }.get(value, value)
            if value and value not in colors:
                colors.append(value)
    return description[:5000], colors[:10]


def normalize_mark_language(result: dict[str, Any]) -> tuple[str, str]:
    """Очистить транслитерацию и перевод, не добавляя догадок от сервера."""
    transliteration = " ".join(str(result.get("transliteration") or "").split()).strip()
    translation = " ".join(str(result.get("translation") or "").split()).strip()
    return transliteration[:200], translation[:200]
