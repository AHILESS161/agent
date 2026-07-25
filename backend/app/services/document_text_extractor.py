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


def extract_from_path(path) -> str:
    """Утилита для тестов: читает файл по пути (str или Path)."""
    p = Path(path)
    return extract_text_from_bytes(p.read_bytes(), p.name)