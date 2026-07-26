"""Сверка извлечённых полей с полями заявления.

Логика вынесена из эндпоинта, потому что нужна в двух местах: в самом
бланке заявления, где специалист видит и правит значения, и в старом
ответе сверки, который пока сохраняется для совместимости.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.document_processing.extractors.registry import (
    ExtractedFieldResult,
    FieldCandidateResult,
)
from app.document_processing.mappers import build_reconciliation
from app.document_processing.mappers.field_mapping import MappingRow
from app.infrastructure.database.models import (
    ExtractedField,
    ExtractionMethod,
    TrademarkApplicationDraft,
)


async def load_reconciliation(
    session: AsyncSession, application_id: int
) -> tuple[list[MappingRow], dict[str, int]]:
    """Построить таблицу сверки по делу.

    Возвращает строки сверки и соответствие «путь поля -> его
    идентификатор в базе»: без идентификатора значение нельзя принять
    или изменить.
    """
    application = (
        await session.execute(
            select(TrademarkApplicationDraft)
            .options(selectinload(TrademarkApplicationDraft.client))
            .where(TrademarkApplicationDraft.id == application_id)
        )
    ).scalar_one_or_none()
    if application is None:
        return [], {}

    stored = list(
        (
            await session.execute(
                select(ExtractedField)
                .where(ExtractedField.application_id == application_id)
                .options(selectinload(ExtractedField.candidates))
            )
        )
        .scalars()
        .all()
    )

    domain = [
        ExtractedFieldResult(
            field_id=field.field_path,
            label=field.label or field.field_path,
            status=field.status,
            is_sensitive=field.is_sensitive,
            value=field.raw_value,
            normalized_value=field.normalized_value,
            confidence=field.confidence,
            page_number=field.page_number,
            pattern_id=field.pattern_id,
            source_snippet=field.source_snippet or "",
            validation_error=field.validation_error,
            extraction_method=field.extraction_method,
            candidates=[
                FieldCandidateResult(
                    raw_value=candidate.raw_value,
                    normalized_value=candidate.normalized_value or "",
                    pattern_id=candidate.pattern_id or "",
                    confidence=candidate.confidence or 0.0,
                    page_number=candidate.page_number,
                    validation_passed=candidate.validation_passed,
                )
                for candidate in field.candidates
            ],
        )
        for field in stored
    ]

    # Значения карточки дела нужны, чтобы увидеть расхождение
    # с документом, а не молча его перекрыть.
    case_values = {
        "case.applicant.full_name": (
            application.client.full_name_or_company_name if application.client else None
        ),
        "case.applicant.inn": application.client.inn if application.client else None,
        "case.applicant.ogrn": (
            application.client.ogrn_or_ogrnip if application.client else None
        ),
    }
    case_values = {key: value for key, value in case_values.items() if value}

    client_type = application.client.type.value if application.client else None
    rows, _ = build_reconciliation(domain, case_values, client_type=client_type)

    field_ids = {field.field_path: field.id for field in stored}
    return rows, field_ids


def custom_fields(stored: list[ExtractedField], mapped_paths: set[str]):
    """Поля, заведённые специалистом сверх маппинга."""
    return [
        field
        for field in stored
        if field.field_path not in mapped_paths
        and field.extraction_method is ExtractionMethod.manual
    ]
