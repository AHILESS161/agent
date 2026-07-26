"""Смысловое сходство обозначений, в том числе на разных языках.

Пункт 42 Правил № 482 относит к смысловому сходству подобие заложенных
в обозначениях понятий и идей, а также совпадение значения обозначений
в разных языках. Регулярные выражения этого не видят: «ЯБЛОКО» и «APPLE»
не совпадают ни звучанием, ни начертанием, ни набором слов — но значат
одно и то же, и для однородных товаров это прямое основание по пункту 6
статьи 1483 ГК РФ.

Это то место в оценке сходства, где языковая модель действительно нужна:
перевод и понятийное тождество — семантическая задача, справочником
её не закрыть. Остальные критерии пункта 42 считаются детерминированно
(см. ``document_processing.similarity``) и моделью не пересчитываются.

Дисциплина вызовов:

* модель спрашивается только там, где её ответ способен изменить вывод:
  если звукового сходства и так достаточно либо товары заведомо
  неоднородны, вызова не будет;
* ответ может только повысить смысловое сходство, но не понизить
  рассчитанное правилами — отказ, ошибка или неразобранный ответ
  возвращают систему к детерминированной оценке;
* вид связи выбирается из закрытого списка; свободный текст модели
  попадает в объяснение для специалиста, но не в числовую оценку.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.agents.legal.rag_analyzer import _parse_json
from app.core.logging import get_logger
from app.document_processing.similarity import SimilarityAssessment

logger = get_logger(__name__)


class SemanticRelation(str, Enum):
    """Вид смысловой связи между обозначениями."""

    translation = "translation"
    transliteration = "transliteration"
    same_concept = "same_concept"
    related_concept = "related_concept"
    unrelated = "unrelated"


# Числовые веса задаются здесь, а не моделью: иначе оценка перестала бы
# быть воспроизводимой. Модель отвечает на вопрос «какая связь»,
# шкалу применяют правила.
_RELATION_SCORES: dict[SemanticRelation, float] = {
    SemanticRelation.translation: 0.90,
    SemanticRelation.transliteration: 0.85,
    SemanticRelation.same_concept: 0.80,
    SemanticRelation.related_concept: 0.45,
    SemanticRelation.unrelated: 0.0,
}

_RELATION_LABELS: dict[SemanticRelation, str] = {
    SemanticRelation.translation: "прямой перевод",
    SemanticRelation.transliteration: "транслитерация",
    SemanticRelation.same_concept: "одно и то же понятие",
    SemanticRelation.related_concept: "близкие понятия",
    SemanticRelation.unrelated: "смысловой связи не установлено",
}

# Ниже этого порога звукового или графического сходства смысловая
# проверка бессмысленна: обозначения и так признаны сходными.
_MARK_SIMILARITY_CEILING = 0.75

# Ниже этой однородности товаров смысловое совпадение не изменит вывод:
# по пункту 162 Пленума смешение требует и сходства, и однородности.
_GOODS_FLOOR = 0.4

# Слишком короткие или несловесные обозначения модель оценить не может.
_MIN_MEANINGFUL_CHARS = 2

SYSTEM_PROMPT = """Ты — лингвист-эксперт, помогающий патентному
поверенному оценить смысловое сходство двух обозначений.

Твоя единственная задача — определить, означают ли два обозначения одно
и то же понятие, в том числе если они записаны на разных языках или
разными алфавитами.

СТРОГИЕ ПРАВИЛА:

1. Ответь СТРОГО валидным JSON без пояснений вокруг.
2. Поле relation выбирается ТОЛЬКО из списка:
   - "translation" — одно обозначение является переводом другого
     (ЯБЛОКО / APPLE, ЗВЕЗДА / STELLA);
   - "transliteration" — та же лексема, записанная другим алфавитом
     (ЗВЕЗДА / ZVEZDA, BOSCH / БОШ);
   - "same_concept" — обозначения выражают одно понятие иными словами
     (МОРЖ / ПОЛЯРНЫЙ ЗВЕРЬ);
   - "related_concept" — понятия близки, но не тождественны
     (ЯБЛОКО / ГРУША — оба фрукты, но это разные плоды);
   - "unrelated" — смысловой связи нет.
3. Если хотя бы одно обозначение не имеет словарного значения
   (выдуманное слово, аббревиатура, набор букв) — relation "unrelated".
4. При сомнении выбирай "unrelated". Ошибочно найденная связь вреднее,
   чем пропущенная: специалист проверяет то, что ты нашёл.
5. Обязательно укажи значение каждого обозначения в полях
   left_meaning и right_meaning. Если значения нет — пустая строка.
6. Не оценивай звуковое и графическое сходство: это считается без тебя.
7. Не делай выводов о регистрации знака и о вероятности смешения.

Схема ответа:
{
  "relation": "translation|transliteration|same_concept|related_concept|unrelated",
  "left_meaning": "значение первого обозначения",
  "right_meaning": "значение второго обозначения",
  "rationale": "одно предложение: почему выбрана такая связь"
}"""

USER_TEMPLATE = """Обозначение 1: {left}
Обозначение 2: {right}

Определи смысловую связь между ними."""


@dataclass
class SemanticVerdict:
    """Результат смысловой проверки пары обозначений."""

    relation: SemanticRelation
    score: float
    rationale: str
    left_meaning: str = ""
    right_meaning: str = ""
    llm_used: bool = False
    model_name: str | None = None

    @property
    def is_meaningful(self) -> bool:
        """Установлена ли связь, которую стоит показывать специалисту."""
        return self.relation is not SemanticRelation.unrelated

    def as_dict(self) -> dict:
        return {
            "relation": self.relation.value,
            "relation_label": _RELATION_LABELS[self.relation],
            "score": round(self.score, 3),
            "left_meaning": self.left_meaning,
            "right_meaning": self.right_meaning,
            "rationale": self.rationale,
            "llm_used": self.llm_used,
            "model_name": self.model_name,
        }


def unrelated_verdict(reason: str) -> SemanticVerdict:
    """Заключение «связи нет» без обращения к модели."""
    return SemanticVerdict(
        relation=SemanticRelation.unrelated,
        score=0.0,
        rationale=reason,
        llm_used=False,
    )


def _has_letters(text: str) -> bool:
    return bool(re.search(r"[^\W\d_]", text or ""))


def needs_semantic_check(
    assessment: SimilarityAssessment,
    left: str,
    right: str,
    goods_known: bool = True,
) -> bool:
    """Способна ли смысловая проверка изменить вывод по этой паре.

    Модель вызывается только тогда, когда ответ имеет значение:
    обозначения ещё не признаны сходными по звуку и начертанию,
    но товары достаточно однородны, чтобы смысловое совпадение
    привело к риску смешения.

    ``goods_known=False`` означает, что классы МКТУ ещё не определены.
    Тогда однородность не опровергнута, а лишь неизвестна, и порог
    по товарам не применяется: пропустить смысловое совпадение только
    потому, что перечень классов не заполнен, — хуже, чем проверить.
    """
    if assessment.mark_similarity >= _MARK_SIMILARITY_CEILING:
        return False  # сходство уже установлено правилами
    if goods_known and assessment.goods < _GOODS_FLOOR:
        return False  # даже полное совпадение смысла не даст смешения
    if assessment.semantic >= _RELATION_SCORES[SemanticRelation.same_concept]:
        return False  # совпадение слов уже найдено детерминированно

    for text in (left, right):
        stripped = (text or "").strip()
        if len(stripped) < _MIN_MEANINGFUL_CHARS or not _has_letters(stripped):
            return False
    return True


class SemanticSimilarityAnalyzer:
    """Смысловое сравнение пары обозначений языковой моделью."""

    def __init__(self, llm_provider) -> None:
        self._llm = llm_provider

    async def analyze(self, left: str, right: str) -> SemanticVerdict:
        """Определить смысловую связь. При любой неудаче — «связи нет»."""
        raw = await self._call_llm(
            USER_TEMPLATE.format(left=left.strip(), right=right.strip())
        )
        if not raw:
            return unrelated_verdict("Модель недоступна: смысловая проверка не выполнена")

        parsed = _parse_json(raw)
        if not isinstance(parsed, dict):
            logger.warning("Смысловая проверка: ответ модели не разобран")
            return unrelated_verdict("Ответ модели не разобран")

        try:
            relation = SemanticRelation(str(parsed.get("relation", "")).strip())
        except ValueError:
            # Модель вернула связь вне закрытого списка — доверять нельзя.
            logger.warning(
                "Смысловая проверка: недопустимый вид связи",
                relation=str(parsed.get("relation"))[:40],
            )
            return unrelated_verdict("Модель вернула недопустимый вид связи")

        return SemanticVerdict(
            relation=relation,
            score=_RELATION_SCORES[relation],
            rationale=str(parsed.get("rationale", "")).strip()[:500],
            left_meaning=str(parsed.get("left_meaning", "")).strip()[:200],
            right_meaning=str(parsed.get("right_meaning", "")).strip()[:200],
            llm_used=True,
            model_name=getattr(self._llm, "MODEL_NAME", None),
        )

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
                    max_tokens=400,
                )
            else:
                response = await self._llm.complete(
                    prompt=prompt, system=SYSTEM_PROMPT, temperature=0.0
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка вызова LLM в смысловой проверке", error=str(exc))
            return None

        if isinstance(response, str):
            return response
        return getattr(response, "content", None) or getattr(response, "text", None)


def describe(verdict: SemanticVerdict, left: str, right: str) -> str:
    """Объяснение для специалиста: что именно нашла модель."""
    if not verdict.is_meaningful:
        return ""
    parts = [
        f"Смысловая связь: {_RELATION_LABELS[verdict.relation]} "
        f"(«{left}» — «{right}»)."
    ]
    if verdict.left_meaning and verdict.right_meaning:
        parts.append(
            f"Значения: «{left}» — {verdict.left_meaning}; "
            f"«{right}» — {verdict.right_meaning}."
        )
    if verdict.rationale:
        parts.append(verdict.rationale)
    parts.append(
        "Смысловое сходство определено языковой моделью и требует "
        "проверки специалистом."
    )
    return " ".join(parts)
