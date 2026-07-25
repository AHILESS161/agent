"""Файловое хранилище оригиналов загруженных документов.

Ответственность:
    - проверка расширения, размера и РЕАЛЬНОГО типа файла по сигнатуре
      (magic bytes), а не по заявленному Content-Type или расширению;
    - защита от path traversal при сохранении;
    - адресация по SHA-256, чтобы один и тот же файл не дублировался
      на диске и чтобы содержимое можно было сверить с записью в БД.

Хранилище локальное (каталог на диске). Интерфейс намеренно узкий —
``save``/``read``/``delete``/``check_storage`` — чтобы замена на S3/MinIO
не затрагивала вызывающий код.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.core.config import settings


class FileValidationError(ValueError):
    """Файл не прошёл проверку: тип, размер или повреждённое содержимое."""


# ---------------------------------------------------------------------------
# Допустимые типы MVP
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}
)

# Сигнатуры (magic bytes) → канонический MIME.
# DOCX — это ZIP, поэтому отличается от прочих ZIP только по содержимому.
_SIGNATURES: Final[tuple[tuple[bytes, str], ...]] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"PK\x03\x04", "application/zip"),  # уточняется ниже до DOCX
)

_EXT_TO_MIME: Final[dict[str, str]] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_SAFE_NAME_RE: Final[re.Pattern[str]] = re.compile(r"[^\w\s.\-()]+", re.UNICODE)


@dataclass(frozen=True)
class StoredFile:
    """Результат сохранения файла."""

    stored_path: str
    sha256: str
    size: int
    detected_mime: str
    extension: str


# ---------------------------------------------------------------------------
# Определение типа
# ---------------------------------------------------------------------------

def detect_mime(content: bytes, filename: str) -> str:
    """Определить MIME по содержимому файла.

    Расширение используется только как подсказка для форматов без
    надёжной сигнатуры (TXT) и для уточнения ZIP → DOCX.
    """
    ext = Path(filename).suffix.lower()

    for signature, mime in _SIGNATURES:
        if content.startswith(signature):
            if mime == "application/zip":
                # DOCX — ZIP, внутри которого есть word/document.xml.
                if b"word/" in content[:4096] or ext == ".docx":
                    return _EXT_TO_MIME[".docx"]
                return "application/zip"
            return mime

    # У TXT сигнатуры нет — проверяем, что это действительно текст.
    if ext == ".txt":
        # CP1251 — однобайтовая кодировка и декодирует почти любые байты,
        # поэтому одной успешной декодировки мало: сначала отсекаем
        # содержимое с управляющими символами, которых в тексте не бывает.
        if b"\x00" in content:
            raise FileValidationError(
                "Файл с расширением .txt содержит нулевые байты — это не текст"
            )
        control_bytes = sum(
            1 for b in content if b < 0x09 or 0x0E <= b < 0x20
        )
        if control_bytes > len(content) * 0.01:
            raise FileValidationError(
                "Файл с расширением .txt содержит управляющие символы — это не текст"
            )
        for encoding in ("utf-8", "cp1251"):
            try:
                content.decode(encoding)
                return "text/plain"
            except UnicodeDecodeError:
                continue
        raise FileValidationError(
            "Файл с расширением .txt не является текстом в UTF-8 или CP1251"
        )

    return "application/octet-stream"


def validate_upload(content: bytes, filename: str) -> tuple[str, str]:
    """Проверить загружаемый файл. Вернуть ``(extension, detected_mime)``.

    Поднимает :class:`FileValidationError` при любом несоответствии.
    """
    if not filename or not filename.strip():
        raise FileValidationError("Имя файла не указано")

    if not content:
        raise FileValidationError("Файл пуст")

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise FileValidationError(
            f"Файл слишком большой: {len(content) / 1024 / 1024:.1f} МБ "
            f"(максимум {settings.MAX_UPLOAD_MB} МБ)"
        )

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"Недопустимый тип файла: {ext or '(без расширения)'}. "
            f"Разрешены: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    detected = detect_mime(content, filename)
    expected = _EXT_TO_MIME[ext]
    if detected != expected:
        # Расширение расходится с содержимым — типичный признак
        # переименованного или повреждённого файла.
        raise FileValidationError(
            f"Содержимое файла не соответствует расширению {ext}: "
            f"обнаружен тип {detected}, ожидался {expected}"
        )

    return ext, detected


# ---------------------------------------------------------------------------
# Хранилище
# ---------------------------------------------------------------------------

def get_storage_root() -> Path:
    return Path(settings.FILE_STORAGE_PATH).resolve()


def normalize_upload_filename(filename: str) -> str:
    """Починить имя файла, пришедшее в multipart как latin-1.

    Браузеры передают имя файла сырыми UTF-8 байтами, а python-multipart
    декодирует заголовки как latin-1. Из-за этого «Выписка.pdf» приезжает
    как «Âûïèñêà.pdf». Для русскоязычной системы это заметная проблема.

    Обратное преобразование безопасно: для ASCII-имён оно ничего не меняет,
    а для корректно декодированного UTF-8 обрывается на encode() и
    возвращает исходную строку.
    """
    if not filename:
        return filename
    try:
        return filename.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return filename


def _safe_filename(filename: str) -> str:
    """Убрать из имени всё, что может увести запись за пределы каталога."""
    name = Path(filename).name  # отбрасывает любые ../ и абсолютные пути
    name = _SAFE_NAME_RE.sub("_", name).strip()
    return name[:200] or "file"


def save_upload(content: bytes, filename: str) -> StoredFile:
    """Проверить и сохранить файл. Путь адресуется по SHA-256.

    Повторная загрузка того же содержимого не создаёт копию на диске.
    """
    ext, detected_mime = validate_upload(content, filename)

    digest = hashlib.sha256(content).hexdigest()
    root = get_storage_root()
    # Двухуровневый шардинг, чтобы каталог не разрастался.
    target_dir = root / digest[:2] / digest[2:4]
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / f"{digest}{ext}"
    if not target.exists():
        target.write_bytes(content)

    # Проверка на выход за пределы хранилища — страховка на случай,
    # если конфигурация пути изменится.
    resolved = target.resolve()
    if not resolved.is_relative_to(root):
        raise FileValidationError("Недопустимый путь сохранения файла")

    return StoredFile(
        stored_path=str(resolved.relative_to(root)).replace("\\", "/"),
        sha256=digest,
        size=len(content),
        detected_mime=detected_mime,
        extension=ext,
    )


def read_file(stored_path: str) -> bytes:
    """Прочитать файл по относительному пути из хранилища."""
    root = get_storage_root()
    target = (root / stored_path).resolve()
    if not target.is_relative_to(root):
        raise FileValidationError("Попытка выхода за пределы хранилища")
    if not target.exists():
        raise FileNotFoundError(f"Файл не найден: {stored_path}")
    return target.read_bytes()


def delete_file(stored_path: str) -> bool:
    """Удалить файл. Возвращает True, если файл существовал."""
    root = get_storage_root()
    target = (root / stored_path).resolve()
    if not target.is_relative_to(root):
        raise FileValidationError("Попытка выхода за пределы хранилища")
    if target.exists():
        target.unlink()
        return True
    return False


def check_storage() -> tuple[bool, str | None]:
    """Проверить, что хранилище доступно на запись. Для /ready."""
    try:
        root = get_storage_root()
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_probe"
        probe.write_bytes(b"ok")
        probe.unlink()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"Файловое хранилище недоступно на запись: {exc}"
