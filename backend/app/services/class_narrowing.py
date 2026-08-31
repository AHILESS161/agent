"""Model-assisted narrowing of an official Nice class list.

The model may only choose positions supplied by the official catalogue.  It
never writes the final goods/services wording itself, which prevents invented
or paraphrased terms from leaking into the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.infrastructure.llm.base import LLMMessage


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "selected_indices": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "One-based numbers of suitable catalogue positions",
        },
        "rationale": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["selected_indices", "rationale", "assumptions"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class NarrowingResult:
    selected_items: tuple[str, ...]
    rationale: str
    assumptions: tuple[str, ...]


class InvalidNarrowingResult(ValueError):
    """The provider answered, but did not return a usable grounded selection."""


def _messages(
    *,
    class_number: int,
    business_description: str,
    goods_services: str,
    candidates: tuple[str, ...],
) -> list[LLMMessage]:
    numbered = "\n".join(f"{index}. {item}" for index, item in enumerate(candidates, 1))
    return [
        LLMMessage(
            role="system",
            content=(
                "Вы помогаете подготовить перечень товаров и услуг для заявки на товарный знак. "
                "Выбирайте только позиции из переданного официального перечня МКТУ. Нельзя менять "
                "формулировки, дописывать новые позиции или выбирать смежные услуги на всякий случай. "
                "Оставляйте позицию, только если она прямо соответствует описанной текущей или явно "
                "планируемой деятельности заявителя. Верните только JSON по заданной схеме."
            ),
        ),
        LLMMessage(
            role="user",
            content=(
                f"Класс МКТУ: {class_number}\n\n"
                f"Описание деятельности:\n{business_description or 'не указано'}\n\n"
                f"Товары и услуги со слов заявителя:\n{goods_services or 'не указаны'}\n\n"
                "Выберите все и только те позиции, которые прямо подходят. Укажите их номера "
                "в selected_indices. Если данных недостаточно для осмысленного выбора, верните "
                "пустой список и объясните это в rationale.\n\n"
                f"Официальные позиции:\n{numbered}"
            ),
        ),
    ]


def _validate(raw: Any, candidates: tuple[str, ...]) -> NarrowingResult:
    if not isinstance(raw, dict):
        raise InvalidNarrowingResult("Модель не вернула структурированный результат")
    indices = raw.get("selected_indices")
    if not isinstance(indices, list):
        raise InvalidNarrowingResult("Модель не указала выбранные позиции")

    normalized: list[int] = []
    for value in indices:
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidNarrowingResult("Модель вернула некорректные номера позиций")
        if not 1 <= value <= len(candidates):
            raise InvalidNarrowingResult("Модель сослалась на позицию вне официального перечня")
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise InvalidNarrowingResult(
            str(raw.get("rationale") or "По описанию не удалось выбрать подходящие позиции")
        )

    rationale = str(raw.get("rationale") or "").strip()
    assumptions_raw = raw.get("assumptions") or []
    assumptions = tuple(
        str(item).strip()
        for item in assumptions_raw
        if isinstance(item, str) and item.strip()
    )
    return NarrowingResult(
        selected_items=tuple(candidates[index - 1] for index in normalized),
        rationale=rationale,
        assumptions=assumptions,
    )


async def narrow_class_items(
    llm_provider: Any,
    *,
    class_number: int,
    business_description: str,
    goods_services: str,
    candidates: tuple[str, ...],
) -> NarrowingResult:
    """Select a grounded subset, retrying with the configured fallback if needed."""
    if not candidates:
        raise InvalidNarrowingResult("В справочнике нет позиций для этого класса")
    if not business_description.strip() and not goods_services.strip():
        raise InvalidNarrowingResult(
            "Сначала опишите деятельность или перечислите товары и услуги"
        )

    messages = _messages(
        class_number=class_number,
        business_description=business_description,
        goods_services=goods_services,
        candidates=candidates,
    )
    try:
        raw = await llm_provider.generate_structured(
            messages=messages,
            output_schema=OUTPUT_SCHEMA,
            temperature=0.0,
        )
        return _validate(raw, candidates)
    except InvalidNarrowingResult:
        fallback = getattr(llm_provider, "fallback", None)
        if fallback is None or not hasattr(fallback, "generate_structured"):
            raise
        raw = await fallback.generate_structured(
            messages=messages,
            output_schema=OUTPUT_SCHEMA,
            temperature=0.0,
        )
        return _validate(raw, candidates)


def validate_official_items(
    selected_items: list[str], candidates: tuple[str, ...]
) -> tuple[str, ...]:
    """Validate a client-confirmed preview against the official catalogue."""
    official = set(candidates)
    result: list[str] = []
    for raw in selected_items:
        item = raw.strip()
        if not item or item not in official:
            raise InvalidNarrowingResult(
                "Список содержит позицию, которой нет в официальном перечне класса"
            )
        if item not in result:
            result.append(item)
    if not result:
        raise InvalidNarrowingResult("Нужно оставить хотя бы одну позицию")
    return tuple(result)
