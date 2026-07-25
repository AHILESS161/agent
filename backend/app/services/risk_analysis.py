"""Прогон анализа рисков и сохранение результата с прослеживаемостью.

Связывает RAG-анализатор с базой данных. Сохраняется не только вывод,
но и всё, что нужно для его воспроизведения: версия базы знаний,
имя модели, режим поиска, использованные фрагменты и результат проверки
каждой цитаты — включая отклонённые.

Отклонённые цитаты сохраняются намеренно: специалист должен видеть,
что именно система не приняла и почему.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.legal.rag_analyzer import AnalysisOutcome, RagAbsoluteGroundsAnalyzer
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.database.models import (
    AnalysisCitation,
    AnalysisKind,
    CitationStatus,
    RiskAssessment,
    RiskFinding,
    RiskLevel,
    SearchMode,
    TrademarkApplicationDraft,
)
from app.infrastructure.rag.citations import verify_all
from app.infrastructure.rag.store import knowledge_base_version, load_active_chunks

logger = get_logger(__name__)

# Идентификатор фрагмента в контексте модели: "kb-<id чанка>".
_CITATION_ID_RE = re.compile(r"^kb-(\d+)$")


@dataclass
class AnalysisContext:
    """Факты дела, передаваемые анализатору."""

    mark_text: str | None
    mark_type: str | None
    description: str | None
    goods_services: str | None
    classes: str | None

    @classmethod
    def from_application(
        cls, application: TrademarkApplicationDraft
    ) -> "AnalysisContext":
        return cls(
            mark_text=application.mark_text or application.mark_name,
            mark_type=application.mark_type.value if application.mark_type else None,
            description=application.description_of_mark,
            goods_services=application.goods_services_raw,
            classes=None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "mark_text": self.mark_text,
            "mark_type": self.mark_type,
            "description": self.description,
            "goods_services": self.goods_services,
            "classes": self.classes,
        }

    @property
    def is_sufficient(self) -> bool:
        """Минимум для осмысленного анализа — само обозначение."""
        return bool(self.mark_text and self.mark_text.strip())


def _chunk_id_from_ref(source_ref: str | None) -> int | None:
    if not source_ref:
        return None
    match = _CITATION_ID_RE.match(source_ref)
    return int(match.group(1)) if match else None


async def run_absolute_grounds_analysis(
    session: AsyncSession,
    application: TrademarkApplicationDraft,
    llm_provider: Any,
    user_id: int | None = None,
) -> RiskAssessment:
    """Выполнить анализ абсолютных оснований и сохранить результат."""
    context = AnalysisContext.from_application(application)
    chunks = await load_active_chunks(session)
    kb_version = await knowledge_base_version(session)

    assessment = RiskAssessment(
        application_id=application.id,
        analysis_kind=AnalysisKind.absolute_grounds,
        knowledge_base_version=kb_version,
        model_name=getattr(settings, "LLM_MODEL", None),
        llm_used=True,
        # Поиск по реестру в этом виде анализа не выполняется:
        # абсолютные основания оцениваются по нормативным материалам.
        search_mode=SearchMode.not_performed,
        requires_specialist_review=True,
        created_by_user_id=user_id,
    )

    # --- недостаточно данных дела ---
    if not context.is_sufficient:
        assessment.is_inconclusive = True
        assessment.inconclusive_reason = (
            "Недостаточно подтверждённых данных для вывода."
        )
        assessment.missing_data_json = ["Заявляемое обозначение не указано"]
        assessment.limitations_json = [
            "Анализ не проводился: в деле отсутствует обозначение"
        ]
        session.add(assessment)
        await session.flush()
        return assessment

    # --- пустая база знаний ---
    if not chunks:
        assessment.is_inconclusive = True
        assessment.inconclusive_reason = (
            "Недостаточно подтверждённых данных для вывода."
        )
        assessment.missing_data_json = ["База знаний пуста"]
        assessment.limitations_json = [
            "Анализ невозможен: нормативные материалы не проиндексированы. "
            "Выполните: python -m scripts.ingest_knowledge"
        ]
        session.add(assessment)
        await session.flush()
        return assessment

    analyzer = RagAbsoluteGroundsAnalyzer(llm_provider, chunks)
    outcome: AnalysisOutcome = await analyzer.analyse(context.as_dict())

    assessment.sources_used_json = outcome.sources_used
    assessment.verification_json = outcome.verification

    if not outcome.is_conclusive:
        assessment.is_inconclusive = True
        assessment.inconclusive_reason = (
            outcome.insufficient.message if outcome.insufficient else None
        )
        assessment.missing_data_json = (
            outcome.insufficient.missing_data if outcome.insufficient else []
        )
        assessment.limitations_json = [
            outcome.insufficient.reason
            if outcome.insufficient and outcome.insufficient.reason
            else "Вывод не сформирован"
        ]
        session.add(assessment)
        await session.flush()
        logger.info(
            "Анализ не дал обоснованных выводов",
            application_id=application.id,
            reason=assessment.inconclusive_reason,
        )
        return assessment

    result = outcome.result
    assessment.overall_risk = RiskLevel(result.overall_risk.value)
    assessment.summary = result.summary
    assessment.limitations_json = list(result.limitations)
    assessment.missing_data_json = list(result.missing_data)
    session.add(assessment)
    await session.flush()

    # Карта источников для повторной проверки цитат при сохранении.
    available = {
        chunk.citation_id: chunk.content
        for chunk in chunks
        if chunk.citation_id in set(outcome.sources_used)
    }

    for finding_data in result.findings:
        finding = RiskFinding(
            assessment_id=assessment.id,
            category=finding_data.category.value,
            level=RiskLevel(finding_data.level.value),
            legal_basis=finding_data.legal_basis,
            explanation=finding_data.explanation,
            case_facts_json=list(finding_data.case_facts_used),
            missing_data_json=list(finding_data.missing_data),
            confidence=finding_data.confidence,
            recommended_action=finding_data.recommended_action,
            citations_verified=bool(finding_data.citations_verified),
            verification_json=finding_data.verification_summary,
        )
        session.add(finding)
        await session.flush()

        report = verify_all(
            [c.model_dump() for c in finding_data.citations], available
        )
        for check in report.checks:
            session.add(
                AnalysisCitation(
                    finding_id=finding.id,
                    knowledge_chunk_id=_chunk_id_from_ref(check.source_id),
                    source_ref=check.source_id,
                    quote=check.quote,
                    anchor=check.anchor,
                    status=CitationStatus(check.status.value),
                    matched_ratio=check.matched_ratio,
                )
            )

    await session.flush()
    logger.info(
        "Анализ рисков выполнен",
        application_id=application.id,
        assessment_id=assessment.id,
        findings=len(result.findings),
        overall_risk=assessment.overall_risk.value,
    )
    return assessment


def serialize_assessment(assessment: RiskAssessment) -> dict[str, Any]:
    """Представление оценки рисков для API и отчёта."""
    return {
        "id": assessment.id,
        "application_id": assessment.application_id,
        "analysis_kind": assessment.analysis_kind.value,
        "overall_risk": assessment.overall_risk.value if assessment.overall_risk else None,
        "summary": assessment.summary,
        "is_inconclusive": assessment.is_inconclusive,
        "inconclusive_reason": assessment.inconclusive_reason,
        "limitations": assessment.limitations_json or [],
        "missing_data": assessment.missing_data_json or [],
        "requires_specialist_review": assessment.requires_specialist_review,
        # Сведения для воспроизводимости вывода.
        "provenance": {
            "knowledge_base_version": assessment.knowledge_base_version,
            "model_name": assessment.model_name,
            "llm_used": assessment.llm_used,
            "search_mode": assessment.search_mode.value,
            "sources_used": assessment.sources_used_json or [],
            "verification": assessment.verification_json or {},
        },
        "created_at": assessment.created_at.isoformat() if assessment.created_at else None,
        "findings": [
            {
                "id": finding.id,
                "category": finding.category,
                "level": finding.level.value,
                "legal_basis": finding.legal_basis,
                "explanation": finding.explanation,
                "case_facts": finding.case_facts_json or [],
                "missing_data": finding.missing_data_json or [],
                "confidence": finding.confidence,
                "recommended_action": finding.recommended_action,
                "citations_verified": finding.citations_verified,
                "verification": finding.verification_json or {},
                "reviewer_decision": (
                    finding.reviewer_decision.value
                    if finding.reviewer_decision
                    else None
                ),
                "reviewer_comment": finding.reviewer_comment,
                "citations": [
                    {
                        "id": citation.id,
                        "source_ref": citation.source_ref,
                        "knowledge_chunk_id": citation.knowledge_chunk_id,
                        "quote": citation.quote,
                        "anchor": citation.anchor,
                        "status": citation.status.value,
                        "matched_ratio": citation.matched_ratio,
                        # Отклонённые цитаты показываются явно.
                        "is_trustworthy": citation.status
                        in (CitationStatus.verified, CitationStatus.partial),
                    }
                    for citation in finding.citations
                ],
            }
            for finding in assessment.findings
        ],
        "disclaimer": (
            "Результаты сформированы с применением AI и носят предварительный "
            "информационный характер. Они требуют проверки специалистом."
        ),
    }
