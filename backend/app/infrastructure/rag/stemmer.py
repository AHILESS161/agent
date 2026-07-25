"""Упрощённый стеммер русского языка (алгоритм Snowball).

Зачем. Русский язык сильно флективен: в норме написано «гербами,
флагами, государственными», а специалист ищет «герб, флаг,
государственная». При точном сравнении токенов совпадений нет вовсе,
и релевантный фрагмент закона не попадает в контекст модели.

Проверено на базе знаний проекта: без стемминга запрос про
государственную символику не поднимал пункт 4 статьи 1483, где она
как раз и описана.

Реализация не требует внешних зависимостей и детерминирована.
"""

from __future__ import annotations

import re
from functools import lru_cache

_VOWELS = "аеиоуыэюя"

# Окончания по группам алгоритма Snowball для русского языка.
_PERFECTIVE_GERUND_1 = ("вшись", "вши", "в")
_PERFECTIVE_GERUND_2 = (
    "ившись", "ывшись", "ивши", "ывши", "ив", "ыв",
)
_ADJECTIVE = (
    "ими", "ыми", "его", "ему", "ого", "ому", "ых", "их", "ая", "яя",
    "ою", "ею", "ее", "ие", "ые", "ое", "ей", "ий", "ый", "ой", "ем",
    "им", "ым", "ом", "ух", "юю", "ую", "ю", "ья", "ье", "ья",
)
_PARTICIPLE_1 = ("ем", "нн", "вш", "ющ", "щ")
_PARTICIPLE_2 = ("ивш", "ывш", "ующ")
_REFLEXIVE = ("ся", "сь")
_VERB_1 = (
    "ла", "на", "ете", "йте", "ли", "й", "л", "ем", "н", "ло", "но",
    "ет", "ют", "ны", "ть", "ешь", "нно",
)
_VERB_2 = (
    "ила", "ыла", "ена", "ейте", "уйте", "ите", "или", "ыли", "ей",
    "уй", "ил", "ыл", "им", "ым", "ен", "ило", "ыло", "ено", "ят",
    "ует", "уют", "ит", "ыт", "ены", "ить", "ыть", "ишь", "ую", "ю",
)
_NOUN = (
    "а", "ев", "ов", "ие", "ье", "е", "иями", "ями", "ами", "еи", "ии",
    "и", "ией", "ей", "ой", "ий", "й", "иям", "ям", "ием", "ем", "ам",
    "ом", "о", "у", "ах", "иях", "ях", "ы", "ь", "ию", "ью", "ю", "ия",
    "ья", "я",
)
_SUPERLATIVE = ("ейш", "ейше")
_DERIVATIONAL = ("ост", "ость")


def _find_rv(word: str) -> int:
    """RV — область после первой гласной."""
    for index, char in enumerate(word):
        if char in _VOWELS:
            return index + 1
    return len(word)


def _find_r2(word: str) -> int:
    """R2 — область после второй последовательности гласная-согласная."""
    r1 = len(word)
    for index in range(len(word) - 1):
        if word[index] in _VOWELS and word[index + 1] not in _VOWELS:
            r1 = index + 2
            break
    r2 = len(word)
    for index in range(r1, len(word) - 1):
        if word[index] in _VOWELS and word[index + 1] not in _VOWELS:
            r2 = index + 2
            break
    return r2


def _strip(word: str, region_start: int, endings: tuple[str, ...]) -> tuple[str, bool]:
    """Отсечь самое длинное подходящее окончание в пределах области."""
    region = word[region_start:]
    for ending in sorted(endings, key=len, reverse=True):
        if region.endswith(ending):
            return word[: len(word) - len(ending)], True
    return word, False


def _strip_after_a_ya(
    word: str, region_start: int, endings: tuple[str, ...]
) -> tuple[str, bool]:
    """Отсечь окончание, только если ему предшествует «а» или «я»."""
    region = word[region_start:]
    for ending in sorted(endings, key=len, reverse=True):
        if not region.endswith(ending):
            continue
        cut = len(word) - len(ending)
        if cut > 0 and word[cut - 1] in "ая":
            return word[:cut], True
    return word, False


@lru_cache(maxsize=20000)
def stem(word: str) -> str:
    """Привести слово к основе.

    Слова короче четырёх букв не обрабатываются: у них отсечение
    окончания чаще вредит, чем помогает.
    """
    word = word.lower().replace("ё", "е")
    if len(word) < 4 or not re.match(r"^[а-я]+$", word):
        return word

    rv = _find_rv(word)
    r2 = _find_r2(word)

    # Шаг 1: деепричастие, либо возвратность + прилагательное/глагол/существительное.
    result, changed = _strip(word, rv, _PERFECTIVE_GERUND_2)
    if not changed:
        # Группа «в», «вши», «вшись» отсекается только после «а» или «я».
        # Без этого условия «гербов» превращалось в «гербо»,
        # а не в «герб», и словоформы переставали совпадать.
        result, changed = _strip_after_a_ya(word, rv, _PERFECTIVE_GERUND_1)

    if not changed:
        stripped, _ = _strip(word, rv, _REFLEXIVE)
        result = stripped

        adjectival, changed = _strip(result, rv, _ADJECTIVE)
        if changed:
            result = adjectival
            participle, _ = _strip(result, rv, _PARTICIPLE_2)
            if participle == result:
                result, _ = _strip(result, rv, _PARTICIPLE_1)
            else:
                result = participle
        else:
            verb, changed = _strip(result, rv, _VERB_2)
            if not changed:
                verb, changed = _strip(result, rv, _VERB_1)
            if changed:
                result = verb
            else:
                result, _ = _strip(result, rv, _NOUN)

    # Шаг 2: убрать конечное «и».
    if result.endswith("и"):
        result = result[:-1]

    # Шаг 3: словообразовательный суффикс в R2.
    if len(result) > r2:
        derivational, _ = _strip(result, r2, _DERIVATIONAL)
        result = derivational

    # Шаг 4: превосходная степень, удвоенное «н», мягкий знак.
    if result.endswith("нн"):
        result = result[:-1]
    else:
        superlative, changed = _strip(result, rv, _SUPERLATIVE)
        if changed:
            result = superlative
            if result.endswith("нн"):
                result = result[:-1]
    if result.endswith("ь"):
        result = result[:-1]

    return result
