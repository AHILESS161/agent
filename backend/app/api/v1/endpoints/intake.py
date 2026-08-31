"""
Intake endpoints — загрузка и парсинг заполненной формы заявки Роспатента.

Поддерживает:
    POST /api/v1/intake/parse-application        — multipart с файлом
    POST /api/v1/intake/parse-application-text   — JSON с уже извлечённым текстом

Эти endpoint'ы НЕ создают заявку в БД. Они возвращают распарсенный dict,
который клиент использует для предзаполнения формы создания заявки.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.agents.intake.application_pdf_parser import ApplicationPdfParserAgent
from app.api.dependencies import _get_llm_provider, _get_prompt_registry
from app.core.security import get_current_user
from app.document_processing.classifier import classify_document
from app.document_processing.extractors import extract_registry_fields
from app.document_processing.passport import extract_passport_prefill
from app.infrastructure.database.models import DocumentKind, User
from app.services import file_storage
from app.schemas.intake import (
    ParseApplicationFromTextRequest,
    ParsedApplicationResponse,
)
from app.services.document_text_extractor import (
    NoTextLayerError,
    UnsupportedDocumentType,
    extract_pages_from_bytes,
    extract_text_from_bytes,
)
from app.services.text_encoding import repair_utf8_mojibake

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intake", tags=["intake"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

# Тип документа -> какой набор паттернов извлечения применять.
_PREFILL_PATTERNS: dict[DocumentKind, str] = {
    DocumentKind.egrul_extract: "egrul",
    DocumentKind.egrip_extract: "egrip",
    DocumentKind.unknown_registry_extract: "egrul",
}

# Тип документа -> предлагаемый тип клиента для формы приёма.
_CLIENT_TYPE_BY_KIND: dict[DocumentKind, str] = {
    DocumentKind.egrul_extract: "company",
    DocumentKind.egrip_extract: "sole_proprietor",
}

# Куда в форме приёма ложится каждое извлечённое поле. Одно и то же
# поле формы («ИНН», «ОГРН/ОГРНИП») заполняется из разных реестровых
# полей в зависимости от типа документа.
_FORM_TARGET: dict[str, str] = {
    "registry.legal_entity.full_name": "name",
    "registry.legal_entity.short_name": "short_name",
    "registry.legal_entity.inn": "inn",
    "registry.legal_entity.ogrn": "ogrn",
    "registry.legal_entity.kpp": "kpp",
    "registry.legal_entity.address.full": "address",
    "registry.legal_entity.director.last_name": "signatory_last_name",
    "registry.legal_entity.director.first_name": "signatory_first_name",
    "registry.legal_entity.director.middle_name": "signatory_middle_name",
    "registry.legal_entity.director.position": "signatory_position",
    "registry.sole_proprietor.full_name": "name",
    "registry.sole_proprietor.last_name": "signatory_last_name",
    "registry.sole_proprietor.first_name": "signatory_first_name",
    "registry.sole_proprietor.middle_name": "signatory_middle_name",
    "registry.sole_proprietor.inn": "inn",
    "registry.sole_proprietor.ogrnip": "ogrn",
    "registry.sole_proprietor.main_activity": "business_activity",
}


async def _run_parser(raw_text: str, use_llm: bool) -> ParsedApplicationResponse:
    registry = _get_prompt_registry()
    llm = _get_llm_provider()
    agent = ApplicationPdfParserAgent(registry, llm)
    output = await agent.run({"raw_text": raw_text, "use_llm": use_llm})
    data = output.findings or {}
    # Агент кладёт полный результат в findings["parsed"]; разворачиваем.
    parsed = data.get("parsed") or data
    return ParsedApplicationResponse(
        client=parsed.get("client", {}),
        application=parsed.get("application", {}),
        representative=parsed.get("representative", {}),
        priority=parsed.get("priority", {}),
        confidence=parsed.get("confidence", {}),
        warnings=parsed.get("warnings", []),
        source_text_length=parsed.get("source_text_length", len(raw_text)),
        extraction_method=parsed.get("extraction_method", "heuristic+llm_fallback"),
    )


@router.post(
    "/parse-application",
    response_model=ParsedApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def parse_application(
    file: UploadFile = File(..., description="PDF/DOCX заполненной заявки"),
    use_llm: bool = False,
    _current_user: User = Depends(get_current_user),
) -> ParsedApplicationResponse:
    """Парсит загруженный файл формы заявки (PDF или DOCX).

    Ничего не сохраняет — результат используется для предзаполнения формы.
    Для загрузки документа в дело есть ``POST /applications/{id}/documents``.

    ``use_llm`` по умолчанию выключен: сначала детерминированные правила,
    LLM — только явным запросом как fallback.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указано имя файла",
        )

    content = await file.read()
    # Тип проверяется по сигнатуре содержимого, а не по расширению.
    try:
        file_storage.validate_upload(content, file.filename)
    except file_storage.FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    t0 = time.perf_counter()
    try:
        raw_text = extract_text_from_bytes(content, file.filename)
    except UnsupportedDocumentType as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Text extraction failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Не удалось извлечь текст: {exc}",
        ) from exc

    if not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл не содержит извлекаемого текста (возможно, это скан без OCR)",
        )

    response = await _run_parser(raw_text, use_llm)
    response.source_filename = file.filename
    logger.info(
        "parse_application: file=%s chars=%d elapsed=%.2fs",
        file.filename,
        len(raw_text),
        time.perf_counter() - t0,
    )
    return response


@router.post(
    "/prefill-registrant",
    status_code=status.HTTP_200_OK,
    summary="Извлечь данные заявителя из выписки для предзаполнения формы приёма",
)
async def prefill_registrant(
    file: UploadFile = File(..., description="Выписка ЕГРЮЛ или ЕГРИП (PDF/DOCX/TXT)"),
    _current_user: User = Depends(get_current_user),
) -> dict:
    """Разобрать выписку и вернуть предложения для формы приёма.

    Ничего не сохраняет и не создаёт: разбор идёт в памяти,
    извлечённые значения не логируются. Тип документа и все значения
    требуют проверки специалистом — форма их лишь предзаполняет,
    решение остаётся за юристом. Сам документ прикрепляется к делу
    отдельно, при его создании.

    Извлечение детерминированное (regex по подписям полей), без LLM.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Не указано имя файла"
        )

    content = await file.read()
    try:
        file_storage.validate_upload(content, file.filename)
    except file_storage.FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # --- текст ---
    try:
        pages = extract_pages_from_bytes(content, file.filename)
    except (NoTextLayerError, UnsupportedDocumentType) as exc:
        # Скан без текстового слоя — реальный и частый случай. Это не
        # ошибка сервера: форму просто заполняют вручную.
        return {
            "document_kind": None,
            "client_type": None,
            "prefill": {},
            "fields": [],
            "warning": (
                "В документе нет текстового слоя (возможно, это скан или фото). "
                "Автозаполнение недоступно — заполните поля вручную."
            ),
            "notice": _PREFILL_NOTICE,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("prefill: не удалось разобрать файл: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Не удалось разобрать файл (возможно, он повреждён): {exc}",
        ) from exc

    # Некоторые PDF-генераторы отдают UTF-8 как Latin-1 (``ÐÐÐ©...``).
    # Чиним текст до классификации и regex-извлечения, иначе повреждённое
    # наименование сразу попадёт в карточку клиента.
    normalized_pages = [
        (p.page_number, repair_utf8_mojibake(p.text) or "") for p in pages
    ]
    full_text = "\n".join(text for _, text in normalized_pages)
    classification = classify_document(full_text)
    pattern_set = _PREFILL_PATTERNS.get(classification.kind)

    if classification.kind is DocumentKind.passport:
        passport_fields = extract_passport_prefill(full_text)
        fields = [
            {
                "field_id": item.field_id,
                "label": item.label,
                "value": item.value,
                "confidence": 0.75,
                "is_sensitive": True,
                "form_target": item.form_target,
                "page_number": None,
            }
            for item in passport_fields
        ]
        prefill = {item.form_target: item.value for item in passport_fields}
        return {
            "document_kind": classification.kind.value,
            "kind_confidence": classification.confidence,
            "client_type": "individual",
            "prefill": prefill,
            "fields": fields,
            "warning": None if fields else (
                "Паспорт распознан, но ФИО и адрес не удалось надёжно прочитать. "
                "Документ можно сохранить в деле, а поля заполнить вручную."
            ),
            "notice": (
                "Из паспорта предложены только ФИО и адрес регистрации. "
                "Серия, номер, дата рождения, сведения о выдаче и код подразделения "
                "не переносятся в заявление. Проверьте предложенные значения по документу."
            ),
        }

    if pattern_set is None:
        # Тип не распознан или для него нет правил (доверенность,
        # изображение, паспорт-скан и т. п.). Форму заполняют вручную.
        return {
            "document_kind": classification.kind.value,
            "kind_confidence": classification.confidence,
            "client_type": _CLIENT_TYPE_BY_KIND.get(classification.kind),
            "prefill": {},
            "fields": [],
            "warning": (
                "Тип документа не распознан как выписка ЕГРЮЛ/ЕГРИП — "
                "автозаполнение недоступно. Проверьте документ и заполните "
                "форму вручную."
            ),
            "notice": _PREFILL_NOTICE,
        }

    results = extract_registry_fields(normalized_pages, pattern_set)

    prefill: dict[str, str] = {}
    fields: list[dict] = []
    for result in results:
        value = result.normalized_value or result.value
        if not value or result.validation_error:
            continue
        target = _FORM_TARGET.get(result.field_id)
        fields.append(
            {
                "field_id": result.field_id,
                "label": result.label,
                "value": value,
                "confidence": result.confidence,
                "is_sensitive": result.is_sensitive,
                "form_target": target,
                "page_number": result.page_number,
            }
        )
        # В форму кладём первое непустое значение на каждое целевое поле.
        if target and target not in prefill:
            prefill[target] = value

    logger.info(
        "prefill-registrant: kind=%s pattern=%s fields=%d",
        classification.kind.value,
        pattern_set,
        len(fields),
    )

    return {
        "document_kind": classification.kind.value,
        "kind_confidence": classification.confidence,
        "client_type": _CLIENT_TYPE_BY_KIND.get(classification.kind),
        "prefill": prefill,
        "fields": fields,
        "warning": None,
        "notice": _PREFILL_NOTICE,
    }


_PREFILL_NOTICE = (
    "Данные извлечены автоматически и требуют проверки специалистом. "
    "Ни одно значение не подтверждено. Проверьте их по документу перед "
    "созданием дела."
)


@router.post(
    "/parse-application-text",
    response_model=ParsedApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def parse_application_text(
    payload: ParseApplicationFromTextRequest,
    _current_user: User = Depends(get_current_user),
) -> ParsedApplicationResponse:
    """Парсит уже извлечённый текст формы (используется в тестах и в e2e)."""
    response = await _run_parser(payload.raw_text, payload.use_llm)
    response.source_filename = "<raw_text>"
    return response
