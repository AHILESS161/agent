"""Определение типа документа по его тексту — без LLM.

Тип определяется по устойчивым заголовкам и обязательным реквизитам,
характерным для каждого вида документа. Если уверенных признаков нет,
документ помечается ``unknown_registry_extract`` или ``unknown`` и
требует подтверждения специалистом — угадывать тип запрещено.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.infrastructure.database.models import DocumentKind


@dataclass(frozen=True)
class ClassificationResult:
    kind: DocumentKind
    confidence: float
    matched_markers: list[str] = field(default_factory=list)
    requires_confirmation: bool = True
    reason: str = ""


@dataclass(frozen=True)
class _Rule:
    kind: DocumentKind
    # Маркеры, каждый из которых — сильный признак данного типа.
    strong: tuple[str, ...] = ()
    # Вспомогательные маркеры, повышающие уверенность.
    weak: tuple[str, ...] = ()


_RULES: tuple[_Rule, ...] = (
    _Rule(
        kind=DocumentKind.egrul_extract,
        strong=(
            r"единого\s+государственного\s+реестра\s+юридических\s+лиц",
            r"выписка\s+из\s+егрюл",
        ),
        weak=(
            r"\bогрн\b",
            r"полное\s+наименование",
            r"сведения\s+о\s+регистрирующем\s+органе",
            r"уставн\w*\s+капитал",
            r"без\s+доверенности",
        ),
    ),
    _Rule(
        kind=DocumentKind.egrip_extract,
        strong=(
            r"единого\s+государственного\s+реестра\s+индивидуальных\s+предпринимателей",
            r"выписка\s+из\s+егрип",
        ),
        weak=(
            r"\bогрнип\b",
            r"индивидуальн\w+\s+предпринимател",
        ),
    ),
    _Rule(
        kind=DocumentKind.trademark_application,
        strong=(
            r"на\s+государственную\s+регистрацию\s+товарного\s+знака",
            r"заявляемое\s+обозначение",
        ),
        weak=(
            r"\(731\)",
            r"\(540\)",
            r"\(511\)",
            r"мкту",
            r"по\s+интеллектуальной\s+собственности",
        ),
    ),
    _Rule(
        kind=DocumentKind.power_of_attorney,
        strong=(r"^\s*доверенность\b", r"\bнастоящей\s+доверенностью\b"),
        weak=(r"уполномочива", r"сроком\s+на"),
    ),
)

# Признаки того, что перед нами реестровая справка неустановленного вида:
# реквизиты есть, но заголовок не опознан.
_REGISTRY_HINTS = (r"\bогрн\b", r"\bогрнип\b", r"\bинн\b", r"\bкпп\b", r"реестр")


def classify_document(text: str) -> ClassificationResult:
    """Определить тип документа по тексту.

    Возвращает результат с уверенностью и списком сработавших маркеров,
    чтобы решение было объяснимым и проверяемым специалистом.
    """
    if not text or not text.strip():
        return ClassificationResult(
            kind=DocumentKind.unknown,
            confidence=0.0,
            requires_confirmation=True,
            reason="Пустой текст — тип определить невозможно",
        )

    haystack = re.sub(r"\s+", " ", text.lower())

    best: ClassificationResult | None = None
    for rule in _RULES:
        strong_hits = [p for p in rule.strong if re.search(p, haystack, re.IGNORECASE)]
        weak_hits = [p for p in rule.weak if re.search(p, haystack, re.IGNORECASE)]
        if not strong_hits:
            continue

        # Базовая уверенность за сильный маркер + добавка за каждый слабый.
        confidence = min(0.95, 0.7 + 0.05 * len(weak_hits) + 0.05 * (len(strong_hits) - 1))
        candidate = ClassificationResult(
            kind=rule.kind,
            confidence=round(confidence, 2),
            matched_markers=strong_hits + weak_hits,
            # Тип всегда подтверждается специалистом: цена ошибки —
            # реквизиты из непрофильного документа в заявлении.
            requires_confirmation=True,
            reason=f"Совпали заголовочные маркеры: {len(strong_hits)} сильных, {len(weak_hits)} вспомогательных",
        )
        if best is None or candidate.confidence > best.confidence:
            best = candidate

    if best is not None:
        return best

    # Заголовок не опознан, но реквизиты присутствуют.
    hints = [p for p in _REGISTRY_HINTS if re.search(p, haystack, re.IGNORECASE)]
    if len(hints) >= 2:
        return ClassificationResult(
            kind=DocumentKind.unknown_registry_extract,
            confidence=0.3,
            matched_markers=hints,
            requires_confirmation=True,
            reason=(
                "Найдены реестровые реквизиты, но заголовок документа не опознан. "
                "Требуется ручное подтверждение типа."
            ),
        )

    return ClassificationResult(
        kind=DocumentKind.unknown,
        confidence=0.0,
        requires_confirmation=True,
        reason="Устойчивых признаков известных типов документов не найдено",
    )
