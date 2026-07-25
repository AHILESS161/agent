"""Строгие схемы вывода AI-агента.

Ответ модели валидируется до записи в БД и до показа специалисту.
Невалидный ответ отбрасывается — лучше отсутствие вывода, чем
правдоподобный текст без основания.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class GroundCategory(str, Enum):
    """Категории оснований для отказа (ГК РФ, ст. 1483)."""

    no_distinctiveness = "no_distinctiveness"       # п.1: нет различительной способности
    descriptive = "descriptive"                     # п.1: описательность
    common_use = "common_use"                       # п.1: вошло во всеобщее употребление
    misleading = "misleading"                       # п.3: вводит в заблуждение
    against_public_interest = "against_public_interest"  # п.2: общественные интересы, мораль
    official_symbols = "official_symbols"           # п.4: государственная символика
    conflicting_mark = "conflicting_mark"           # п.6: сходство с чужим знаком
    other = "other"


class Citation(BaseModel):
    """Ссылка на фрагмент базы знаний.

    ``source_id`` обязателен: без него цитату невозможно проверить,
    а непроверяемая цитата равносильна её отсутствию.
    """

    source_id: str = Field(min_length=1, description="Идентификатор фрагмента базы знаний")
    quote: str = Field(min_length=10, description="Дословный фрагмент из источника")
    anchor: Optional[str] = Field(default=None, description="Напр. «ст. 1483, п. 1»")

    @field_validator("quote")
    @classmethod
    def quote_must_be_substantive(cls, value: str) -> str:
        if len(value.split()) < 4:
            raise ValueError(
                "Цитата слишком короткая: по ней невозможно проверить вывод"
            )
        return value


class RiskFinding(BaseModel):
    """Один установленный риск."""

    category: GroundCategory
    level: RiskLevel
    legal_basis: str = Field(min_length=3, description="Норма, напр. «ГК РФ ст. 1483 п. 1»")
    explanation: str = Field(min_length=20, description="Объяснение вывода")
    case_facts_used: list[str] = Field(
        default_factory=list,
        description="Факты дела, на которых основан вывод",
    )
    citations: list[Citation] = Field(
        default_factory=list, description="Подтверждающие фрагменты базы знаний"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    missing_data: list[str] = Field(
        default_factory=list, description="Чего не хватает для уверенного вывода"
    )
    recommended_action: Optional[str] = None

    # Заполняется системой после проверки цитат, а не моделью.
    citations_verified: Optional[bool] = None
    verification_summary: Optional[dict] = None

    @field_validator("confidence")
    @classmethod
    def confidence_is_never_absolute(cls, value: float) -> float:
        # Уверенность 1.0 недопустима: это предварительная оценка,
        # а не установленный факт.
        return min(value, 0.95)


class AnalysisResult(BaseModel):
    """Полный результат анализа обозначения."""

    overall_risk: RiskLevel
    summary: str = Field(min_length=20)
    findings: list[RiskFinding] = Field(default_factory=list)

    # Ограничения анализа — обязательны и не могут быть пустыми.
    limitations: list[str] = Field(min_length=1)
    missing_data: list[str] = Field(default_factory=list)

    # Признак, что вывод требует проверки специалистом.
    # Значение False недопустимо: система не даёт окончательных заключений.
    requires_specialist_review: bool = True

    @field_validator("requires_specialist_review")
    @classmethod
    def always_requires_review(cls, value: bool) -> bool:
        return True


class InsufficientData(BaseModel):
    """Ответ, когда данных или источников недостаточно.

    Обязательная альтернатива выводу: агент не должен додумывать.
    """

    message: str = "Недостаточно подтверждённых данных для вывода."
    missing_data: list[str] = Field(default_factory=list)
    reason: Optional[str] = None
    requires_specialist_review: bool = True


# JSON Schema для передачи модели в промпте.
ANALYSIS_JSON_SCHEMA = AnalysisResult.model_json_schema()
