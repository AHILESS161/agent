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

# Вид знака в терминах бланка: коды 550–558 и 551.
_MARK_KIND_LABELS = {
    "word": "словесный",
    "figurative": "изобразительный",
    "combined": "комбинированный",
    "3d": "объёмный (554)",
    "sound": "звуковой (556)",
    "color": "цветовой (558)",
    "other": "иной",
}

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
    # Перечень товаров для кода 511: (номер класса, наименование).
    # Только подтверждённые специалистом классы: неподтверждённый
    # перечень в заявление попадать не должен.
    classes: list[tuple[str, str]] = field(default_factory=list)

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

    client = application.client
    case_values = {
        "case.applicant.full_name": client.full_name_or_company_name if client else None,
        "case.applicant.inn": client.inn if client else None,
        "case.applicant.ogrn": client.ogrn_or_ogrnip if client else None,
        "case.applicant.legal_address": client.address if client else None,
    }

    engine = FieldMappingEngine()
    for spec in engine.config.get("mappings", []):
        target = spec.get("application_field")
        if not target:
            continue

        label = spec.get("label", target)
        registry_field = spec.get("registry_field")
        required = bool(spec.get("required_for_application", False))

        row = by_path.get(registry_field) if registry_field else None
        case_value = case_values.get(spec.get("case_field"))

        if row is None:
            if case_value:
                # Пользователь уже проверил и сохранил значение в карточке
                # заявителя. Оно не обязано присутствовать в выписке (адрес
                # ИП, например, обычно скрыт в открытой ЕГРИП).
                content.filled.append(
                    FilledField(
                        field_id=target,
                        label=label,
                        value=str(case_value),
                        source="введено пользователем",
                    )
                )
            elif spec.get("default_value"):
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

    # Вид знака отмечается в бланке галочкой, но специалисту нужно
    # видеть выбранное значение и в перечне полей.
    if application.mark_type:
        content.filled.append(
            FilledField(
                field_id="application.mark.kind",
                label="Вид знака",
                value=_MARK_KIND_LABELS.get(
                    application.mark_type.value, application.mark_type.value
                ),
                source="карточка дела",
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
            content.classes.append(
                (str(item.class_number), item.class_description or "")
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


def _find_cell(table, marker: str):
    """Найти ячейку бланка по началу её текста.

    Бланк — одна таблица 118×44 с объединёнными ячейками, поэтому
    позиции ищутся по подписи поля, а не по фиксированным индексам:
    так разметка переживёт мелкие правки формы.
    """
    normalized = marker.replace(" ", " ")
    for row in table.rows:
        for cell in row.cells:
            text = cell.text.strip().replace(" ", " ")
            if text.startswith(normalized):
                return cell
    return None


def _write_into(cell, lines: list[str]) -> bool:
    """Дописать значение в ячейку бланка под её подписью.

    В бланке под каждой подписью оставлен пустой абзац — туда и
    пишется значение. Если пустого абзаца нет, добавляется новый:
    затирать типографский текст формы нельзя.
    """
    if cell is None or not lines:
        return False

    target = None
    for paragraph in cell.paragraphs[1:]:
        if not paragraph.text.strip():
            target = paragraph
            break
    if target is None:
        target = cell.add_paragraph()

    target.add_run("\n".join(lines)).bold = True
    return True


def _fill_goods_table(table, classes: list[tuple[str, str]]) -> bool:
    """Заполнить перечень товаров: класс и наименование (код 511)."""
    header = None
    for index, row in enumerate(table.rows):
        if row.cells[0].text.strip() == "Класс":
            header = index
            break
    if header is None:
        return False

    written = 0
    for offset, (number, goods) in enumerate(classes, start=1):
        position = header + offset
        if position >= len(table.rows):
            break
        row = table.rows[position]
        _write_into(row.cells[0], [number]) or row.cells[0].paragraphs[0].add_run(
            number
        )
        # Наименование товаров занимает правую часть строки.
        value_cell = row.cells[3] if len(row.cells) > 3 else None
        if value_cell is not None:
            _write_into(value_cell, [goods]) or value_cell.paragraphs[0].add_run(goods)
        written += 1
    return written > 0


def render_docx(
    content: DraftContent, application: TrademarkApplicationDraft
) -> bytes:
    """Заполнить официальный бланк заявки подтверждёнными данными.

    Заполняется именно бланк Роспатента (приложение к приказу
    Минэкономразвития), а не собственная форма: документ должен быть
    пригоден к подаче, а не пересказывать её своими словами.

    В документ не добавляется никаких служебных пометок — ни о том,
    что это черновик, ни об использовании AI. Это бланк заявления,
    и посторонний текст в нём недопустим. Предупреждения, перечень
    незаполненных полей и чек-лист живут в интерфейсе, а выгрузка
    закрыта до утверждения специалистом.

    Незаполненные поля остаются пустыми — ровно как в бумажной форме,
    которую специалист дозаполняет вручную.
    """
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Бланк заявления не найден: {TEMPLATE_PATH}")

    document = docx.Document(str(TEMPLATE_PATH))
    table = document.tables[0]

    values = {item.field_id: item.value for item in content.filled}

    # --- (731) заявитель: наименование и адрес ---
    applicant_block = [
        values.get("application.applicant.name", ""),
        values.get("application.applicant.address", ""),
    ]
    _write_into(
        _find_cell(table, "(731)"), [line for line in applicant_block if line]
    )

    # --- идентификаторы заявителя ---
    identifiers: list[str] = []
    for label, field_id in (
        ("ОГРН", "application.applicant.ogrn"),
        ("ИНН", "application.applicant.inn"),
        ("КПП", "application.applicant.kpp"),
    ):
        value = values.get(field_id)
        if value:
            identifiers.append(f"{label}: {value}")
    _write_into(_find_cell(table, "ИДЕНТИФИКАТОРЫ"), identifiers)

    # --- (540) заявляемое обозначение ---
    mark_text = values.get("application.mark.text") or (
        application.mark_text or application.mark_name or ""
    )
    if mark_text:
        anchor = _find_cell(table, "(540)")
        if anchor is not None:
            _write_into(anchor, [mark_text])

    # --- (511) перечень товаров и услуг ---
    if content.classes:
        _fill_goods_table(table, content.classes)

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
