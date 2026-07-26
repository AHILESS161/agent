"""Оценка сходства обозначений до степени смешения.

Реализует критерии пункта 42 Правил (приказ Минэкономразвития России
от 20.07.2015 № 482): звуковое, графическое и смысловое сходство —
и однородность товаров по пункту 162 постановления Пленума ВС РФ № 10.

Расчёт детерминированный. Это сознательный выбор: сходство обозначений
считается по формализованным признакам, а не «на усмотрение модели»,
поэтому результат воспроизводим и его можно проверить.

Единственное исключение — смысловое сходство обозначений на разных
языках: «совпадение значения обозначений в разных языках» из пункта 42
формализовать нечем, и его оценивает языковая модель (см.
``agents.legal.semantic_similarity``). Её ответ подаётся сюда через
``with_semantic`` и может только повысить смысловую оценку: при отказе
модели остаётся расчёт по правилам.

Итоговая оценка следует правилу Пленума: смешение возможно и при низком
сходстве обозначений, если товары идентичны, и наоборот.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

# Транслитерация для сравнения кириллицы с латиницей: «ЗВЕЗДА» и
# «ZVEZDA» фонетически тождественны и должны сопоставляться.
_TRANSLIT: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y",
    "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

# Пары букв, различие которых на слух незначимо.
_PHONETIC_FOLD: list[tuple[str, str]] = [
    ("yu", "u"), ("ya", "a"), ("yo", "o"), ("ye", "e"),
    ("ch", "c"), ("sh", "s"), ("sch", "s"), ("zh", "j"),
    ("ks", "x"), ("kv", "q"),
]

# Визуально схожие символы разных алфавитов.
_HOMOGLYPHS: dict[str, str] = {
    "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o",
    "р": "p", "с": "c", "т": "t", "у": "y", "х": "x",
}


class SimilarityLevel(str, Enum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"
    identical = "identical"


def _normalize(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    return re.sub(r"[^\w\s]", " ", text).strip()


def transliterate(text: str) -> str:
    """Записать кириллическое обозначение латиницей.

    Без фонетических упрощений: результат используется как поисковый
    запрос к реестру, где важно точное написание, а не звучание.
    """
    lowered = (text or "").lower().replace("ё", "е")
    return "".join(_TRANSLIT.get(char, char) for char in lowered)


def _to_phonetic(text: str) -> str:
    """Привести обозначение к сравнимой звуковой форме."""
    text = _normalize(text).replace(" ", "")
    result = "".join(_TRANSLIT.get(char, char) for char in text)
    for source, target in _phonetic_order():
        result = result.replace(source, target)
    # Двойные согласные на слух не различаются: «АЛЛА» и «АЛА».
    return re.sub(r"(.)\1+", r"\1", result)


def _phonetic_order() -> list[tuple[str, str]]:
    # Длинные сочетания заменяются первыми, иначе «sch» распадётся на «sh».
    return sorted(_PHONETIC_FOLD, key=lambda pair: len(pair[0]), reverse=True)


def _to_visual(text: str) -> str:
    """Форма для сравнения написания с учётом схожих начертаний."""
    text = _normalize(text).replace(" ", "")
    return "".join(_HOMOGLYPHS.get(char, char) for char in text)


def levenshtein(left: str, right: str) -> int:
    """Расстояние редактирования."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, lchar in enumerate(left, start=1):
        current = [i]
        for j, rchar in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (lchar != rchar),
                )
            )
        previous = current
    return previous[-1]


def ratio(left: str, right: str) -> float:
    """Похожесть строк от 0 до 1."""
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    distance = levenshtein(left, right)
    return max(0.0, 1.0 - distance / max(len(left), len(right)))


def phonetic_similarity(left: str, right: str) -> float:
    """Звуковое сходство (пункт 42 Правил)."""
    return ratio(_to_phonetic(left), _to_phonetic(right))


def visual_similarity(left: str, right: str) -> float:
    """Графическое сходство: написание с учётом схожих символов."""
    return ratio(_to_visual(left), _to_visual(right))


def semantic_similarity(left: str, right: str) -> float:
    """Смысловое сходство по совпадению значимых слов.

    Полноценный семантический анализ требует словаря значений;
    здесь оценивается пересечение слов и вхождение одного обозначения
    в другое — признаки, прямо названные в пункте 42 Правил.
    """
    left_words = set(_normalize(left).split())
    right_words = set(_normalize(right).split())
    if not left_words or not right_words:
        return 0.0

    overlap = left_words & right_words
    if overlap:
        return len(overlap) / max(len(left_words), len(right_words))

    # Вхождение одного обозначения в другое.
    left_joined = "".join(sorted(left_words))
    right_joined = "".join(sorted(right_words))
    if left_joined in right_joined or right_joined in left_joined:
        return 0.7
    return 0.0


def goods_similarity(
    left_classes: list[int] | None,
    right_classes: list[int] | None,
    left_text: str = "",
    right_text: str = "",
) -> float:
    """Однородность товаров и услуг.

    Учитывается совпадение классов МКТУ и пересечение формулировок.
    Классы 1–34 — товары, 35–45 — услуги: принадлежность к разным
    группам снижает однородность.
    """
    left_set = set(left_classes or [])
    right_set = set(right_classes or [])

    if left_set and right_set:
        if left_set & right_set:
            # Полное совпадение классов — максимальная однородность.
            overlap = len(left_set & right_set) / len(left_set | right_set)
            return min(1.0, 0.6 + 0.4 * overlap)

        left_goods = any(c <= 34 for c in left_set)
        right_goods = any(c <= 34 for c in right_set)
        # Разные классы: товары против услуг менее однородны.
        base = 0.25 if left_goods == right_goods else 0.1
    else:
        base = 0.3  # классы неизвестны — судить не о чем

    text_overlap = semantic_similarity(left_text, right_text)
    return min(1.0, base + 0.4 * text_overlap)


def _level(value: float) -> SimilarityLevel:
    if value >= 0.98:
        return SimilarityLevel.identical
    if value >= 0.75:
        return SimilarityLevel.high
    if value >= 0.5:
        return SimilarityLevel.medium
    if value >= 0.25:
        return SimilarityLevel.low
    return SimilarityLevel.none


@dataclass
class SimilarityAssessment:
    """Результат сравнения двух обозначений."""

    phonetic: float
    visual: float
    semantic: float
    goods: float
    overall: float
    mark_similarity: float
    level: SimilarityLevel
    confusion_likely: bool
    reasons: list[str] = field(default_factory=list)
    # Чем получена смысловая оценка: правилами или языковой моделью.
    # Специалист должен видеть разницу — у этих источников разная цена
    # ошибки и разная проверяемость.
    semantic_source: str = "rules"

    def as_dict(self) -> dict:
        return {
            "phonetic": round(self.phonetic, 3),
            "visual": round(self.visual, 3),
            "semantic": round(self.semantic, 3),
            "semantic_source": self.semantic_source,
            "goods": round(self.goods, 3),
            "mark_similarity": round(self.mark_similarity, 3),
            "overall": round(self.overall, 3),
            "level": self.level.value,
            "confusion_likely": self.confusion_likely,
            "reasons": self.reasons,
        }


def assess(
    applicant_mark: str,
    conflicting_mark: str,
    applicant_classes: list[int] | None = None,
    conflicting_classes: list[int] | None = None,
    applicant_goods: str = "",
    conflicting_goods: str = "",
) -> SimilarityAssessment:
    """Оценить вероятность смешения двух обозначений.

    Следует правилу пункта 162 Пленума ВС РФ № 10: смешение возможно
    и при низком сходстве обозначений, если товары идентичны, и при
    низкой однородности товаров, если обозначения тождественны.
    """
    phonetic = phonetic_similarity(applicant_mark, conflicting_mark)
    visual = visual_similarity(applicant_mark, conflicting_mark)
    semantic = semantic_similarity(applicant_mark, conflicting_mark)
    goods = goods_similarity(
        applicant_classes, conflicting_classes, applicant_goods, conflicting_goods
    )
    return _combine(phonetic, visual, semantic, goods, semantic_source="rules")


def with_semantic(
    assessment: SimilarityAssessment, semantic_score: float
) -> SimilarityAssessment:
    """Пересчитать оценку с учётом смыслового сходства от языковой модели.

    Оценка модели может только повысить смысловое сходство: если она
    ниже рассчитанной правилами, возвращается исходное заключение.
    Так отказ, ошибка или осторожный ответ модели никогда не ослабляют
    вывод, полученный детерминированно.
    """
    if semantic_score <= assessment.semantic:
        return assessment
    return _combine(
        assessment.phonetic,
        assessment.visual,
        semantic_score,
        assessment.goods,
        semantic_source="llm",
    )


def _combine(
    phonetic: float,
    visual: float,
    semantic: float,
    goods: float,
    semantic_source: str,
) -> SimilarityAssessment:
    """Свести признаки в итоговую оценку по правилу пункта 162."""
    # Сходство обозначения определяется наиболее выраженным признаком:
    # достаточно совпадения по одному критерию из трёх.
    mark_similarity = max(phonetic, visual, semantic)

    reasons: list[str] = []
    if phonetic >= 0.75:
        reasons.append(f"высокое звуковое сходство ({phonetic:.2f})")
    if visual >= 0.75:
        reasons.append(f"высокое графическое сходство ({visual:.2f})")
    if semantic >= 0.7:
        source = " по оценке языковой модели" if semantic_source == "llm" else ""
        reasons.append(f"смысловое сходство ({semantic:.2f}){source}")
    if goods >= 0.6:
        reasons.append(f"однородные товары и услуги ({goods:.2f})")

    # Итог: сходство обозначения и однородность товаров усиливают
    # друг друга, поэтому берётся произведение с поправкой.
    overall = mark_similarity * (0.55 + 0.45 * goods)

    confusion_likely = (
        (mark_similarity >= 0.75 and goods >= 0.4)
        or (mark_similarity >= 0.5 and goods >= 0.8)
        or mark_similarity >= 0.98
    )

    if confusion_likely and not reasons:
        reasons.append("совокупность признаков указывает на риск смешения")

    return SimilarityAssessment(
        phonetic=phonetic,
        visual=visual,
        semantic=semantic,
        goods=goods,
        overall=overall,
        mark_similarity=mark_similarity,
        level=_level(overall),
        confusion_likely=confusion_likely,
        reasons=reasons,
        semantic_source=semantic_source,
    )
