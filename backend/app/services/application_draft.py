"""Формирование чернового заявления на регистрацию товарного знака.

Заполняется официальный бланк (приложение № 1 к Требованиям) в формате
DOCX. Исходный формат выбран намеренно: генерировать документ и затем
сохранять его в PDF надёжнее, чем разбирать заполненный PDF обратно.

Главное правило: в документ попадают ТОЛЬКО подтверждённые специалистом
значения. Поле со статусом missing, conflict или needs_review остаётся
пустым, а причина указывается в чек-листе. Черновик юридически значимого
документа не должен содержать непроверенных данных, даже если система
в них уверена.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import docx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models import (
    ApplicationDraft,
    DraftStatus,
    ExtractedField,
    FieldStatus,
    TrademarkApplicationDraft,
)
from app.document_processing.mappers.field_mapping import FieldMappingEngine
from app.services.class_analysis import load_class_context

logger = get_logger(__name__)

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "resources"
    / "application_templates"
    / "trademark_application_blank.docx"
)

SCHEMA_VERSION = "1.0.0"


@dataclass
class FilledField:
    field_id: str
    label: str
    value: str
    source: str


@dataclass
class SkippedField:
    field_id: str
    label: str
    reason: str


@dataclass
class DraftContent:
    """Данные для заполнения бланка."""

    filled: list[FilledField] = field(default_factory=list)
    skipped: list[SkippedField] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)

    def value_of(self, field_id: str) -> str | None:
        for item in self.filled:
            if item.field_id == field_id:
                return item.value
        return None


async def collect_draft_content(
    session: AsyncSession, application: TrademarkApplicationDraft
) -> DraftContent:
    """Собрать значения для заявления из подтверждённых полей дела."""
    content = DraftContent()

    rows = (
        (
            await session.execute(
                select(ExtractedField).where(
                    ExtractedField.application_id == application.id
                )
            )
        )
        .scalars()
        .all()
    )
    by_path = {row.field_path: row for row in rows}

    engine = FieldMappingEngine()
    for spec in engine.config.get("mappings", []):
        target = spec.get("application_field")
        if not target:
            continue

        label = spec.get("label", target)
        registry_field = spec.get("registry_field")
        required = bool(spec.get("required_for_application", False))

        row = by_path.get(registry_field) if registry_field else None

        if row is None:
            if spec.get("default_value"):
                # Значение по умолчанию — предложение, а не факт.
                content.skipped.append(
                    SkippedField(
                        field_id=target,
                        label=label,
                        reason=(
                            f"Значение по умолчанию «{spec['default_value']}» "
                            "не подтверждено специалистом"
                        ),
                    )
                )
            elif required:
                content.skipped.append(
                    SkippedField(
                        field_id=target,
                        label=label,
                        reason="Значение не извлечено из документов",
                    )
                )
            continue

        if row.status is FieldStatus.confirmed:
            content.filled.append(
                FilledField(
                    field_id=target,
                    label=label,
                    value=row.normalized_value or row.raw_value or "",
                    source=(
                        f"{row.extraction_method.value}"
                        + (f", стр. {row.page_number}" if row.page_number else "")
                    ),
                )
            )
            continue

        # Всё, что не подтверждено, в документ не попадает.
        reasons = {
            FieldStatus.conflict: "несколько несовпадающих значений, выбор не сделан",
            FieldStatus.needs_review: "значение требует проверки специалистом",
            FieldStatus.missing: "значение не найдено в документах",
            FieldStatus.matched: "значение извлечено, но не подтверждено специалистом",
            FieldStatus.rejected: "значение отклонено специалистом",
            FieldStatus.left_empty: "специалист оставил поле пустым",
        }
        content.skipped.append(
            SkippedField(
                field_id=target,
                label=label,
                reason=reasons.get(row.status, row.status.value),
            )
        )

    # --- сведения об обозначении берутся из карточки дела ---
    mark_text = application.mark_text or application.mark_name
    if mark_text:
        content.filled.append(
            FilledField(
                field_id="application.mark.text",
                label="Заявляемое обозначение",
                value=mark_text,
                source="карточка дела",
            )
        )
    else:
        content.skipped.append(
            SkippedField(
                field_id="application.mark.text",
                label="Заявляемое обозначение",
                reason="не указано в деле",
            )
        )

    if application.description_of_mark:
        content.filled.append(
            FilledField(
                field_id="application.mark.description",
                label="Описание обозначения",
                value=application.description_of_mark,
                source="карточка дела",
            )
        )

    # --- классы МКТУ ---
    class_context = await load_class_context(session, application.id)
    if class_context.is_confirmed:
        for item in class_context.approved:
            content.filled.append(
                FilledField(
                    field_id=f"application.goods_services.class_{item.class_number}",
                    label=f"Класс {item.class_number}",
                    value=item.class_description or "",
                    source="подтверждено специалистом",
                )
            )
    elif class_context.has_any:
        content.skipped.append(
            SkippedField(
                field_id="application.goods_services",
                label="Перечень товаров и услуг",
                reason="классы МКТУ не подтверждены специалистом",
            )
        )
    else:
        content.skipped.append(
            SkippedField(
                field_id="application.goods_services",
                label="Перечень товаров и услуг",
                reason="классы МКТУ не определены",
            )
        )

    # --- чек-лист недостающего ---
    content.checklist = _build_checklist(content, application)
    return content


def _build_checklist(
    content: DraftContent, application: TrademarkApplicationDraft
) -> list[str]:
    """Что специалисту нужно сделать перед подачей."""
    checklist: list[str] = []

    for item in content.skipped:
        checklist.append(f"{item.label}: {item.reason}")

    # Поля, которые заведомо не берутся из документов.
    if not application.mark_image_file_id:
        checklist.append(
            "Изображение обозначения (540): файл не приложен к делу"
        )
    checklist.append(
        "Вид знака (550), тип приоритета и пункт уплаченной пошлины: "
        "отмечаются вручную — эти отметки не определяются автоматически"
    )
    checklist.append(
        "Адрес для переписки (750) и представитель (740): заполняются вручную"
    )
    checklist.append("Документ об уплате пошлины: приложить перед подачей")
    return checklist


# ---------------------------------------------------------------------------
# Заполнение бланка
# ---------------------------------------------------------------------------

# Куда писать значения: якорь в бланке -> идентификатор поля.
# Ячейка ищется по началу текста, значение дописывается в неё же.
_ANCHOR_MAP: list[tuple[str, str]] = [
    ("(731) ЗАЯВИТЕЛЬ", "application.applicant.name"),
    ("ИДЕНТИФИКАТОРЫ ЗАЯВИТЕЛЯ", "application.applicant.identifiers"),
    ("(540) ЗАЯВЛЯЕМОЕ ОБОЗНАЧЕНИЕ", "application.mark.text"),
]


def _template_hash() -> str | None:
    if not TEMPLATE_PATH.exists():
        return None
    return hashlib.sha256(TEMPLATE_PATH.read_bytes()).hexdigest()


def render_docx(
    content: DraftContent, application: TrademarkApplicationDraft
) -> bytes:
    """Сформировать DOCX чернового заявления.

    Официальный бланк — таблица 118×44. Точное попадание в ячейки
    требует ручной разметки каждой позиции, поэтому на этом этапе
    формируется структурированный документ по разделам бланка
    с кодами INID. Он пригоден для проверки специалистом и для
    последующего переноса в официальную форму.
    """
    document = docx.Document()

    document.add_heading("ЗАЯВКА", level=0)
    document.add_paragraph(
        "на государственную регистрацию товарного знака, знака обслуживания, "
        "коллективного знака"
    )
    warning = document.add_paragraph()
    warning.add_run(
        "ЧЕРНОВИК. Сформирован автоматически из подтверждённых данных дела. "
        "Требует проверки специалистом. Не является поданной заявкой."
    ).bold = True

    document.add_paragraph(
        f"Дело №{application.id} · сформировано "
        f"{datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC"
    )

    document.add_heading("Заполненные сведения", level=1)
    if content.filled:
        table = document.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        header = table.rows[0].cells
        header[0].text = "Поле"
        header[1].text = "Значение"
        header[2].text = "Источник"
        for item in content.filled:
            row = table.add_row().cells
            row[0].text = item.label
            row[1].text = item.value
            row[2].text = item.source
    else:
        document.add_paragraph(
            "Подтверждённых значений нет. Подтвердите поля на вкладке "
            "«Сверка полей»."
        )

    document.add_heading("Поля, оставленные пустыми", level=1)
    document.add_paragraph(
        "Эти поля не заполнены намеренно: в черновик попадают только "
        "подтверждённые значения."
    )
    for item in content.skipped:
        document.add_paragraph(f"{item.label} — {item.reason}", style="List Bullet")

    document.add_heading("Что необходимо сделать перед подачей", level=1)
    for item in content.checklist:
        document.add_paragraph(item, style="List Bullet")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def create_draft(
    session: AsyncSession,
    application: TrademarkApplicationDraft,
    user_id: int | None = None,
) -> ApplicationDraft:
    """Сформировать новую версию чернового заявления."""
    content = await collect_draft_content(session, application)
    payload = render_docx(content, application)

    from app.services import file_storage

    stored = file_storage.save_upload(
        payload, f"application-draft-{application.id}.docx"
    )

    last_version = (
        await session.execute(
            select(func.max(ApplicationDraft.version)).where(
                ApplicationDraft.application_id == application.id
            )
        )
    ).scalar() or 0

    draft = ApplicationDraft(
        application_id=application.id,
        version=last_version + 1,
        status=DraftStatus.draft,
        filled_fields_json=[
            {
                "field_id": item.field_id,
                "label": item.label,
                "value": item.value,
                "source": item.source,
            }
            for item in content.filled
        ],
        skipped_fields_json=[
            {"field_id": item.field_id, "label": item.label, "reason": item.reason}
            for item in content.skipped
        ],
        checklist_json=content.checklist,
        file_path=stored.stored_path,
        file_sha256=stored.sha256,
        template_name=TEMPLATE_PATH.name,
        template_sha256=_template_hash(),
        schema_version=SCHEMA_VERSION,
        mapping_version=FieldMappingEngine().version,
        created_by_user_id=user_id,
    )
    session.add(draft)
    await session.flush()

    logger.info(
        "Черновик заявления сформирован",
        application_id=application.id,
        draft_id=draft.id,
        version=draft.version,
        filled=len(content.filled),
        skipped=len(content.skipped),
    )
    return draft


def serialize_draft(draft: ApplicationDraft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "application_id": draft.application_id,
        "version": draft.version,
        "status": draft.status.value,
        "filled_fields": draft.filled_fields_json or [],
        "skipped_fields": draft.skipped_fields_json or [],
        "checklist": draft.checklist_json or [],
        "file_sha256": draft.file_sha256,
        "provenance": {
            "template_name": draft.template_name,
            "template_sha256": draft.template_sha256,
            "schema_version": draft.schema_version,
            "mapping_version": draft.mapping_version,
        },
        "approved_by_user_id": draft.approved_by_user_id,
        "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
        "exported_at": draft.exported_at.isoformat() if draft.exported_at else None,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        # Экспорт разрешён только после утверждения специалистом.
        "can_export": draft.status
        in (DraftStatus.approved_by_specialist, DraftStatus.exported),
        "notice": (
            "Черновик содержит только подтверждённые значения. "
            "Поля со статусом «конфликт», «требует проверки» или «не найдено» "
            "оставлены пустыми намеренно."
        ),
    }
