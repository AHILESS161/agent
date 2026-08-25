"""Обработка финального ответа reasoning-моделей."""

import pytest
from unittest.mock import AsyncMock

from app.infrastructure.llm.openai_compatible_provider import (
    OpenAICompatibleProvider,
)


def test_extracts_final_content_instead_of_reasoning():
    raw = {
        "choices": [{"message": {"reasoning": "внутренний план", "content": "Ответ"}}]
    }

    assert OpenAICompatibleProvider._extract_text(raw) == "Ответ"


def test_reasoning_without_final_content_is_not_shown_to_user():
    raw = {
        "choices": [{"message": {"reasoning": "внутренний план", "content": ""}}]
    }

    with pytest.raises(ValueError, match="не вернула финальный ответ"):
        OpenAICompatibleProvider._extract_text(raw)


@pytest.mark.asyncio
async def test_image_request_uses_data_url_and_selected_vision_model():
    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1", api_key="secret", model="text-model"
    )
    provider._post = AsyncMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": '{"description":"Подробное описание изображения товарного знака с графическими элементами и текстом.","colors":["синий"]}'
                    }
                }
            ]
        }
    )

    result = await provider.generate_image_structured(
        image=b"image-bytes",
        mime_type="image/png",
        prompt="Опиши знак",
        output_schema={"type": "object"},
        model="vision-model",
    )

    payload = provider._post.await_args.args[0]
    assert payload["model"] == "vision-model"
    assert payload["messages"][1]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    assert result["colors"] == ["синий"]
    await provider.aclose()
