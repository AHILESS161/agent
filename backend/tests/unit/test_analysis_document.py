"""Понятный клиентский документ с результатом предварительной проверки."""

from __future__ import annotations

import io

import docx

from app.infrastructure.database.models import (
    AnalysisKind,
    RiskAssessment,
    RiskLevel,
    SearchMode,
    TrademarkApplicationDraft,
)
from app.services.filing_package import _analysis_document


def test_incomplete_section_has_status_instead_of_undefined_risk_and_decodes_entities():
    application = TrademarkApplicationDraft(
        client_id=1,
        mark_name="Дружелюбный сосед",
        mark_text="Дружелюбный сосед",
    )
    assessments = {
        AnalysisKind.absolute_grounds.value: RiskAssessment(
            application_id=1,
            analysis_kind=AnalysisKind.absolute_grounds,
            overall_risk=RiskLevel.low,
            summary="Явных препятствий не выявлено.",
            is_inconclusive=False,
            search_mode=SearchMode.not_performed,
            classes_confirmed=True,
            requires_specialist_review=True,
        ),
        AnalysisKind.relative_grounds.value: RiskAssessment(
            application_id=1,
            analysis_kind=AnalysisKind.relative_grounds,
            overall_risk=None,
            summary="Поиск&#x20;не завершён.",
            is_inconclusive=True,
            inconclusive_reason="Источник недоступен",
            search_mode=SearchMode.not_performed,
            classes_confirmed=True,
            requires_specialist_review=True,
        ),
    }

    document = docx.Document(io.BytesIO(_analysis_document(application, assessments)))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    assert "Статус проверки: не завершена" in text
    assert "Уровень риска: не определён" not in text
    assert "&#" not in text

