"""Тесты проверки и хранения загружаемых файлов.

Ключевое требование: тип файла определяется по сигнатуре содержимого,
а не по расширению и не по заявленному Content-Type — иначе достаточно
переименовать исполняемый файл в .pdf, чтобы он попал в хранилище.
"""

from __future__ import annotations

import pytest

from app.services import file_storage
from app.services.file_storage import FileValidationError

# Минимальные валидные сигнатуры реальных форматов.
PDF_BYTES = b"%PDF-1.4\n" + b"0" * 200
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 200
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"0" * 200
DOCX_BYTES = b"PK\x03\x04" + b"word/document.xml" + b"0" * 200
TXT_BYTES = "Выписка из ЕГРЮЛ".encode("utf-8")
MP3_BYTES = b"ID3" + b"\x04\x00\x00" + b"0" * 200
WAV_BYTES = b"RIFF" + (200).to_bytes(4, "little") + b"WAVEfmt " + b"0" * 200


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Изолировать хранилище, чтобы тесты не писали в рабочий каталог."""
    monkeypatch.setattr(
        file_storage.settings, "FILE_STORAGE_PATH", str(tmp_path / "docs")
    )
    monkeypatch.setattr(file_storage.settings, "MAX_UPLOAD_MB", 1)
    return tmp_path


class TestMimeDetection:
    @pytest.mark.parametrize(
        ("content", "filename", "expected"),
        [
            (PDF_BYTES, "a.pdf", "application/pdf"),
            (PNG_BYTES, "a.png", "image/png"),
            (JPEG_BYTES, "a.jpg", "image/jpeg"),
            (MP3_BYTES, "a.mp3", "audio/mpeg"),
            (WAV_BYTES, "a.wav", "audio/wav"),
            (TXT_BYTES, "a.txt", "text/plain"),
        ],
    )
    def test_detects_by_signature(self, content, filename, expected):
        assert file_storage.detect_mime(content, filename) == expected

    def test_docx_distinguished_from_plain_zip(self):
        docx = file_storage.detect_mime(DOCX_BYTES, "a.docx")
        assert docx.endswith("wordprocessingml.document")

    def test_txt_in_cp1251_is_accepted(self):
        content = "Общество с ограниченной ответственностью".encode("cp1251")
        assert file_storage.detect_mime(content, "a.txt") == "text/plain"


class TestValidationRejects:
    def test_rejects_extension_content_mismatch(self):
        """PDF, переименованный в .png, должен быть отклонён."""
        with pytest.raises(FileValidationError, match="не соответствует расширению"):
            file_storage.validate_upload(PDF_BYTES, "маскировка.png")

    def test_rejects_executable_extension(self):
        with pytest.raises(FileValidationError, match="Недопустимый тип файла"):
            file_storage.validate_upload(b"MZ\x90\x00", "payload.exe")

    def test_rejects_no_extension(self):
        with pytest.raises(FileValidationError, match="Недопустимый тип файла"):
            file_storage.validate_upload(PDF_BYTES, "файл_без_расширения")

    def test_rejects_empty_file(self):
        with pytest.raises(FileValidationError, match="пуст"):
            file_storage.validate_upload(b"", "a.pdf")

    def test_rejects_missing_filename(self):
        with pytest.raises(FileValidationError, match="Имя файла"):
            file_storage.validate_upload(PDF_BYTES, "")

    def test_rejects_oversized_file(self):
        oversized = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)
        with pytest.raises(FileValidationError, match="слишком большой"):
            file_storage.validate_upload(oversized, "big.pdf")

    def test_rejects_corrupted_pdf(self):
        """Файл без сигнатуры %PDF- не является PDF."""
        with pytest.raises(FileValidationError):
            file_storage.validate_upload("это просто текст".encode("utf-8") * 20, "broken.pdf")

    def test_rejects_truncated_pdf_header(self):
        """Обрезанный заголовок не должен приниматься за PDF."""
        with pytest.raises(FileValidationError):
            file_storage.validate_upload(b"%PD" + b"0" * 100, "truncated.pdf")

    def test_rejects_binary_disguised_as_txt(self):
        with pytest.raises(FileValidationError):
            file_storage.validate_upload(b"\x00\x81\xfe\xff" * 20, "a.txt")

    def test_rejects_audio_with_mismatched_extension(self):
        with pytest.raises(FileValidationError, match="не соответствует расширению"):
            file_storage.validate_upload(MP3_BYTES, "sound.wav")


class TestSaveAndRead:
    def test_saves_and_reads_back_identical_bytes(self):
        stored = file_storage.save_upload(PDF_BYTES, "выписка.pdf")
        assert file_storage.read_file(stored.stored_path) == PDF_BYTES
        assert stored.size == len(PDF_BYTES)
        assert stored.detected_mime == "application/pdf"
        assert len(stored.sha256) == 64

    def test_same_content_is_not_duplicated(self):
        first = file_storage.save_upload(PDF_BYTES, "первый.pdf")
        second = file_storage.save_upload(PDF_BYTES, "второй.pdf")
        assert first.sha256 == second.sha256
        assert first.stored_path == second.stored_path

    def test_different_content_gets_different_path(self):
        first = file_storage.save_upload(PDF_BYTES, "a.pdf")
        second = file_storage.save_upload(PDF_BYTES + b"x", "b.pdf")
        assert first.stored_path != second.stored_path

    def test_path_traversal_in_filename_is_neutralised(self):
        """Имя файла не должно влиять на путь: адресация идёт по SHA-256."""
        stored = file_storage.save_upload(PDF_BYTES, "../../../../etc/passwd.pdf")
        root = file_storage.get_storage_root()
        assert (root / stored.stored_path).resolve().is_relative_to(root)

    def test_read_outside_storage_is_blocked(self):
        with pytest.raises(FileValidationError, match="за пределы"):
            file_storage.read_file("../../../../etc/passwd")

    def test_delete_outside_storage_is_blocked(self):
        with pytest.raises(FileValidationError, match="за пределы"):
            file_storage.delete_file("../../secrets.env")

    def test_delete_removes_file(self):
        stored = file_storage.save_upload(PDF_BYTES, "a.pdf")
        assert file_storage.delete_file(stored.stored_path) is True
        assert file_storage.delete_file(stored.stored_path) is False

    def test_read_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            file_storage.read_file("ab/cd/" + "0" * 64 + ".pdf")


class TestFilenameNormalisation:
    """Браузер шлёт имя файла сырыми UTF-8 байтами, а multipart-парсер
    декодирует их как latin-1 — кириллица приезжает искажённой."""

    def test_repairs_browser_utf8_filename(self):
        original = "Выписка_ЕГРЮЛ_03062020-1.pdf"
        as_received = original.encode("utf-8").decode("latin-1")
        assert file_storage.normalize_upload_filename(as_received) == original

    def test_leaves_ascii_untouched(self):
        assert file_storage.normalize_upload_filename("report.pdf") == "report.pdf"

    def test_leaves_correct_cyrillic_untouched(self):
        assert file_storage.normalize_upload_filename("Выписка.pdf") == "Выписка.pdf"

    def test_leaves_undecodable_untouched_instead_of_corrupting(self):
        """Если это не UTF-8, лучше оставить как есть, чем испортить."""
        received = "Выписка.pdf".encode("cp1251").decode("latin-1")
        assert file_storage.normalize_upload_filename(received) == received

    def test_handles_empty(self):
        assert file_storage.normalize_upload_filename("") == ""


class TestStorageHealth:
    def test_check_storage_reports_writable(self):
        ok, error = file_storage.check_storage()
        assert ok is True
        assert error is None
