"""Варианты поискового запроса к реестру.

Реестр ищет по написанию: на запрос «ЯБЛОКО» знак «APPLE» не вернётся
никогда, каким бы точным ни был последующий расчёт сходства. Поэтому
смыслового сравнения найденных записей недостаточно — переводной знак
надо сначала найти, а для этого искать нужно и по переводу.

Разделение обязанностей то же, что и в остальной оценке:

* транслитерация строится правилами — соответствие букв однозначно;
* перевод запрашивается у языковой модели, потому что словаря значений
  в системе нет;
* всё, что вернула модель, проходит жёсткую проверку формы: длина,
  количество слов, допустимые символы. Непрошедшее отбрасывается.

Варианты нужны только для поиска. На оценку сходства они не влияют:
найденная по переводу запись сравнивается с исходным обозначением
по обычным правилам пункта 42.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.legal.rag_analyzer import _parse_json
from app.core.logging import get_logger
from app.document_processing.similarity import transliterate

logger = get_logger(__name__)

# Ограничения на вариант, пришедший от модели. Поисковый запрос — это
# то, что уйдёт во внешнюю систему, и произвольный текст модели туда
# попадать не должен.
MAX_VARIANTS = 3
MAX_VARIANT_CHARS = 40
MAX_VARIANT_WORDS = 3

_ALLOWED_VARIANT = re.compile(r"^[\w\s\-]+$", re.UNICODE)

SYSTEM_PROMPT = """Ты — лингвист, помогающий составить поисковый запрос
по реестру товарных знаков.

Тебе дано обозначение. Определи, есть ли у него словарное значение,
и если есть — назови его перевод на другой язык (русский или английский,
противоположный языку обозначения).

СТРОГИЕ ПРАВИЛА:

1. Ответь СТРОГО валидным JSON без пояснений вокруг.
2. Если обозначение выдумано, является аббревиатурой, фамилией или
   набором букв — has_meaning: false и пустой список translations.
3. В translations помещай ТОЛЬКО перевод, не синонимы, не ассоциации
   и не однокоренные слова. Максимум 3 значения.
4. Каждый перевод — одно-два слова, без пояснений и скобок.
5. При сомнении возвращай has_meaning: false. Лишний вариант поиска
   стоит времени, а ложный перевод уводит проверку в сторону.

Схема ответа:
{
  "has_meaning": true,
  "meaning": "краткое значение обозначения",
  "translations": ["перевод"]
}"""

USER_TEMPLATE = """Обозначение: {mark}

Определи значение и перевод."""


@dataclass(frozen=True)
class QueryVariant:
    """Написание, по которому имеет смысл искать в реестре."""

    text: str
    # original | transliteration | translation
    kind: str
    llm_used: bool = False

    @property
    def label(self) -> str:
        return {
            "original": "исходное обозначение",
            "transliteration": "транслитерация",
            "translation": "перевод",
        }.get(self.kind, self.kind)


def _clean(value: object) -> str | None:
    """Привести вариант к безопасному виду или отбросить его."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or len(text) > MAX_VARIANT_CHARS:
        return None
    if len(text.split()) > MAX_VARIANT_WORDS:
        return None
    if not _ALLOWED_VARIANT.match(text):
        return None
    return text


def deterministic_variants(mark_text: str) -> list[QueryVariant]:
    """Варианты, которые считаются правилами, без обращения к модели."""
    mark = (mark_text or "").strip()
    variants = [QueryVariant(text=mark, kind="original")]
    if not mark:
        return variants

    latin = transliterate(mark).strip()
    # Если обозначение уже латиницей, транслитерация ничего не меняет.
    if latin and latin.casefold() != mark.casefold():
        variants.append(QueryVariant(text=latin.upper(), kind="transliteration"))
    return variants


class QueryVariantGenerator:
    """Расширение поискового запроса переводом обозначения."""

    def __init__(self, llm_provider=None) -> None:
        self._llm = llm_provider

    async def build(self, mark_text: str) -> list[QueryVariant]:
        """Собрать варианты поиска: правила плюс перевод от модели."""
        variants = deterministic_variants(mark_text)
        if self._llm is None or not (mark_text or "").strip():
            return variants

        seen = {variant.text.casefold() for variant in variants}
        for text in await self._translations(mark_text.strip()):
            if text.casefold() in seen:
                continue
            seen.add(text.casefold())
            variants.append(
                QueryVariant(text=text, kind="translation", llm_used=True)
            )
            if len(seen) > MAX_VARIANTS + 1:
                break
        return variants

    async def _translations(self, mark_text: str) -> list[str]:
        raw = await self._call_llm(USER_TEMPLATE.format(mark=mark_text))
        if not raw:
            return []

        parsed = _parse_json(raw)
        if not isinstance(parsed, dict) or parsed.get("has_meaning") is not True:
            return []

        candidates = parsed.get("translations")
        if not isinstance(candidates, list):
            return []

        cleaned: list[str] = []
        for candidate in candidates[:MAX_VARIANTS]:
            text = _clean(candidate)
            if text is None:
                logger.warning(
                    "Вариант поиска отброшен как недопустимый",
                    value=str(candidate)[:60],
                )
                continue
            cleaned.append(text.upper())
        return cleaned

    async def _call_llm(self, prompt: str) -> str | None:
        try:
            if hasattr(self._llm, "generate"):
                from app.infrastructure.llm.base import LLMMessage

                response = await self._llm.generate(
                    messages=[
                        LLMMessage(role="system", content=SYSTEM_PROMPT),
                        LLMMessage(role="user", content=prompt),
                    ],
                    temperature=0.0,
                    max_tokens=300,
                )
            else:
                response = await self._llm.complete(
                    prompt=prompt, system=SYSTEM_PROMPT, temperature=0.0
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка вызова LLM при подборе вариантов", error=str(exc))
            return None

        if isinstance(response, str):
            return response
        return getattr(response, "content", None) or getattr(response, "text", None)
