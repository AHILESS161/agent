"""
Утилиты извлечения текста из документов приложенной формы заявки.

Поддерживает:
    - PDF  (через pdfplumber)
    - DOCX (через python-docx)
    - TXT  (как fallback, на случай если pdfplumber не справился)

Возвращает чистый текст, пригодный для эвристического и LLM-парсинга.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------

try:
    import pdfplumber
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False

try:
    import docx as _docx  # python-docx
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False


class UnsupportedDocumentType(ValueError):
    """Не удалось распознать формат документа."""


def detect_extension(filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return ".pdf"
    if name.endswith(".docx"):
        return ".docx"
    if name.endswith(".doc"):
        return ".doc"
    if name.endswith(".txt"):
        return ".txt"
    raise UnsupportedDocumentType(f"Unsupported file type: {filename}")


def extract_text_from_bytes(content: bytes, filename: str) -> str:
    """Главная точка входа: принимает байты и имя файла, возвращает текст."""
    ext = detect_extension(filename)
    if ext == ".pdf":
        return extract_pdf_text(content)
    if ext in (".docx", ".doc"):
        return extract_docx_text(content)
    if ext == ".txt":
        return content.decode("utf-8", errors="replace")
    raise UnsupportedDocumentType(f"Unsupported extension: {ext}")


def extract_pdf_text(content: bytes) -> str:
    """Извлекает текст из PDF через pdfplumber."""
    if not _PDFPLUMBER_AVAILABLE:
        raise RuntimeError(
            "pdfplumber is not installed. Run: pip install pdfplumber"
        )

    pages_text: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text)
    result = "\n\n".join(pages_text)
    logger.info("extract_pdf_text: %d pages, %d chars", len(pages_text), len(result))
    return result


def extract_docx_text(content: bytes) -> str:
    """Извлекает текст из DOCX через python-docx.

    Проходим по параграфам и таблицам — таблицы важны для бланков Роспатента,
    потому что часть полей там находится именно в табличной форме.
    """
    if not _DOCX_AVAILABLE:
        raise RuntimeError(
            "python-docx is not installed. Run: pip install python-docx"
        )

    doc = _docx.Document(io.BytesIO(content))
    chunks: list[str] = []

    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if text:
            chunks.append(text)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                cell_text = (cell.text or "").strip()
                if cell_text:
                    chunks.append(cell_text)

    result = "\n".join(chunks)
    logger.info("extract_docx_text: %d chunks, %d chars", len(chunks), len(result))
    return result


@dataclass(frozen=True)
class ExtractedPage:
    """Текст одной страницы с указанием способа получения."""

    page_number: int
    text: str
    method: str            # значение ExtractionMethod
    ocr_confidence: float | None = None


def extract_pages_from_bytes(content: bytes, filename: str) -> list[ExtractedPage]:
    """Постранично извлечь текст, фиксируя способ извлечения.

    Постраничность нужна для прослеживаемости: каждое извлечённое поле
    должно ссылаться на конкретную страницу источника.

    OCR не реализован. Скан (PDF без текстового слоя, изображение)
    осознанно приводит к ошибке, а не к пустому результату, который
    можно принять за «в документе ничего нет».
    """
    ext = detect_extension_for_pages(filename)

    if ext == ".pdf":
        if not _PDFPLUMBER_AVAILABLE:
            raise RuntimeError("pdfplumber не установлен. Выполните: pip install pdfplumber")
        pages: list[ExtractedPage] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                pages.append(
                    ExtractedPage(page_number=index, text=text, method="pdf_text_layer")
                )
        if not any(p.text.strip() for p in pages):
            raise NoTextLayerError(
                "PDF не содержит текстового слоя — вероятно, это скан. "
                "Распознавание сканов (OCR) в текущей версии не поддерживается."
            )
        return pages

    if ext in (".docx", ".doc"):
        # python-docx не даёт разбиения на страницы: разбивку определяет
        # рендерер Word. Возвращаем один блок и честно помечаем его как
        # страницу 1, а не выдумываем границы страниц.
        return [
            ExtractedPage(page_number=1, text=extract_docx_text(content), method="docx_parser")
        ]

    if ext == ".txt":
        for encoding in ("utf-8", "cp1251"):
            try:
                return [
                    ExtractedPage(page_number=1, text=content.decode(encoding), method="plain_text")
                ]
            except UnicodeDecodeError:
                continue
        raise UnsupportedDocumentType("Не удалось декодировать TXT (пробовали UTF-8 и CP1251)")

    if ext in (".png", ".jpg", ".jpeg"):
        raise NoTextLayerError(
            "Извлечение текста из изображений требует OCR, который "
            "в текущей версии не поддерживается. Загрузите PDF или DOCX."
        )

    raise UnsupportedDocumentType(f"Неподдерживаемое расширение: {ext}")


class NoTextLayerError(ValueError):
    """В документе нет извлекаемого текста — нужен OCR."""


def detect_extension_for_pages(filename: str) -> str:
    """Как detect_extension, но допускает также изображения."""
    name = (filename or "").lower()
    for ext in (".pdf", ".docx", ".doc", ".txt", ".png", ".jpeg", ".jpg"):
        if name.endswith(ext):
            return ext
    raise UnsupportedDocumentType(f"Неподдерживаемый тип файла: {filename}")


def extract_from_path(path) -> str:
    """Утилита для тестов: читает файл по пути (str или Path)."""
    p = Path(path)
    return extract_text_from_bytes(p.read_bytes(), p.name)