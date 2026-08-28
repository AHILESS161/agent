"""API-тесты загрузки документов: авторизация, роли, валидация файлов."""

from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from app.services import file_storage
from tests.conftest import login_headers

# Синтаксически корректный PDF с одной пустой страницей.
# Заглушка вида b"%PDF-" + мусор проходит проверку сигнатуры, но не
# разбирается парсером — для положительных сценариев нужен валидный файл.
VALID_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF\n"
)

# Валидная сигнатура, но нечитаемое содержимое.
CORRUPTED_PDF = b"%PDF-1.4\n" + b"0" * 500

PDF_BYTES = VALID_PDF


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        file_storage.settings, "FILE_STORAGE_PATH", str(tmp_path / "docs")
    )
    return tmp_path


@pytest.fixture
async def lawyer_token(client, api_user_factory) -> dict[str, str]:
    """Реальный пользователь в тестовой БД + настоящий токен.

    Синтетический токен из conftest не подходит: get_current_user
    сверяет пользователя с БД, а в in-memory БД его нет.
    """
    await api_user_factory("lawyer-docs@test.ru", UserRole.lawyer)
    return login_headers(client, "lawyer-docs@test.ru")


@pytest.fixture
async def other_lawyer_token(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("other-lawyer-docs@test.ru", UserRole.lawyer)
    return login_headers(client, "other-lawyer-docs@test.ru")


@pytest.fixture
def application_id(client, lawyer_token) -> int:
    """Реальное дело в тестовой БД.

    Без него проверки валидации файла проходили бы по 404 «дело не найдено»,
    то есть по неверной причине.
    """
    client_response = client.post(
        "/api/v1/clients",
        json={"type": "company", "full_name_or_company_name": 'ООО "Тест"'},
        headers=lawyer_token,
    )
    client_id = client_response.json()["id"]
    app_response = client.post(
        "/api/v1/applications",
        json={"client_id": client_id, "mark_name": "ТЕСТ"},
        headers=lawyer_token,
    )
    return app_response.json()["id"]


def _upload(client, headers=None, filename="doc.pdf", content=PDF_BYTES, app_id=1):
    return client.post(
        f"/api/v1/applications/{app_id}/source-documents",
        files={"file": (filename, content, "application/pdf")},
        headers=headers or {},
    )


@pytest.mark.api
class TestUploadRequiresAuth:
    def test_upload_without_token_is_rejected(self, client):
        assert _upload(client).status_code == 401

    def test_upload_with_invalid_token_is_rejected(self, client):
        response = _upload(client, {"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401

    def test_list_without_token_is_rejected(self, client):
        assert client.get("/api/v1/applications/1/source-documents").status_code == 401

    def test_download_without_token_is_rejected(self, client):
        assert client.get("/api/v1/source-documents/1/download").status_code == 401

    def test_pages_without_token_is_rejected(self, client):
        assert client.get("/api/v1/source-documents/1/pages").status_code == 401


@pytest.mark.api
class TestUploadValidation:
    """Проверки выполняются до записи в хранилище."""

    def test_rejects_executable_extension(self, client, lawyer_token, application_id):
        response = _upload(
            client,
            lawyer_token,
            filename="payload.exe",
            content=b"MZ\x90\x00",
            app_id=application_id,
        )
        assert response.status_code == 400
        assert "Недопустимый тип" in response.json()["detail"]

    def test_rejects_content_extension_mismatch(self, client, lawyer_token, application_id):
        """PDF, переименованный в .png."""
        response = _upload(
            client,
            lawyer_token,
            filename="fake.png",
            content=PDF_BYTES,
            app_id=application_id,
        )
        assert response.status_code == 400
        assert "не соответствует расширению" in response.json()["detail"]

    def test_rejects_empty_file(self, client, lawyer_token, application_id):
        response = _upload(client, lawyer_token, content=b"", app_id=application_id)
        assert response.status_code in (400, 422)

    def test_accepts_valid_pdf_and_persists_it(self, client, lawyer_token, application_id):
        """Положительный сценарий: файл сохранён и связан с делом."""
        response = _upload(
            client, lawyer_token, filename="выписка.pdf", app_id=application_id
        )
        assert response.status_code == 201
        body = response.json()
        assert body["application_id"] == application_id
        assert body["detected_mime"] == "application/pdf"
        assert len(body["sha256"]) == 64
        # Тип документа всегда подтверждает специалист.
        assert body["kind_requires_confirmation"] is True

        listing = client.get(
            f"/api/v1/applications/{application_id}/source-documents", headers=lawyer_token
        )
        assert listing.json()["total"] == 1

    def test_extracts_pages_and_classifies_kind(self, client, lawyer_token, application_id):
        """Полный проход: текст извлечён постранично, тип определён правилами.

        Используется TXT: минимальный синтетический PDF не содержит
        текстового слоя, поэтому для проверки извлечения не годится.
        """
        text = (
            "ВЫПИСКА\n"
            "из Единого государственного реестра юридических лиц\n"
            "1 Полное наименование ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ ПРИМЕР\n"
            "13 ОГРН 1000000000000\n"
            "Сведения о регистрирующем органе\n"
        ).encode("utf-8")

        response = client.post(
            f"/api/v1/applications/{application_id}/source-documents",
            files={"file": ("выписка.txt", text, "text/plain")},
            headers=lawyer_token,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["processing_status"] == "extracted"
        assert body["document_kind"] == "egrul_extract"
        assert body["page_count"] == 1
        assert body["char_count"] > 0
        assert body["extraction_method"] == "plain_text"

        pages = client.get(
            f"/api/v1/source-documents/{body['id']}/pages", headers=lawyer_token
        ).json()
        assert pages["total"] == 1
        assert "ОГРН" in pages["items"][0]["text"]
        # OCR не применялся — уверенность не выдумывается.
        assert pages["items"][0]["ocr_confidence"] is None

    def test_corrupted_pdf_fails_gracefully_without_500(
        self, client, lawyer_token, application_id
    ):
        """Повреждённый файл не должен ронять запрос: оригинал сохраняется,
        а специалист получает понятное сообщение."""
        response = _upload(
            client,
            lawyer_token,
            filename="битый.pdf",
            content=CORRUPTED_PDF,
            app_id=application_id,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["processing_status"] == "failed"
        assert body["error_message"]
        assert "warning" in body


@pytest.mark.api
class TestMissingApplication:
    def test_upload_to_missing_application_returns_404(self, client, lawyer_token):
        response = _upload(client, lawyer_token, app_id=999999)
        assert response.status_code == 404

    def test_missing_document_returns_404(self, client, lawyer_token):
        response = client.get("/api/v1/source-documents/999999", headers=lawyer_token)
        assert response.status_code == 404


@pytest.mark.api
class TestDocumentLifecycle:
    def test_delete_document_removes_database_row_and_blob(
        self, client, lawyer_token, application_id
    ):
        uploaded = _upload(client, lawyer_token, app_id=application_id)
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]
        stored_files = [path for path in file_storage.get_storage_root().rglob("*") if path.is_file()]
        assert len(stored_files) == 1

        response = client.delete(
            f"/api/v1/source-documents/{document_id}", headers=lawyer_token
        )

        assert response.status_code == 204
        assert client.get(
            f"/api/v1/source-documents/{document_id}", headers=lawyer_token
        ).status_code == 404
        assert not stored_files[0].exists()

    def test_shared_blob_is_kept_until_last_document_is_deleted(
        self, client, lawyer_token, application_id
    ):
        first = _upload(client, lawyer_token, app_id=application_id).json()
        second = _upload(client, lawyer_token, app_id=application_id).json()
        stored_files = [path for path in file_storage.get_storage_root().rglob("*") if path.is_file()]
        assert len(stored_files) == 1

        assert client.delete(
            f"/api/v1/source-documents/{first['id']}", headers=lawyer_token
        ).status_code == 204
        assert stored_files[0].exists()

        assert client.delete(
            f"/api/v1/source-documents/{second['id']}", headers=lawyer_token
        ).status_code == 204
        assert not stored_files[0].exists()

    def test_delete_application_removes_its_unreferenced_blobs(
        self, client, lawyer_token, application_id
    ):
        assert _upload(client, lawyer_token, app_id=application_id).status_code == 201
        stored_files = [path for path in file_storage.get_storage_root().rglob("*") if path.is_file()]
        assert len(stored_files) == 1

        response = client.delete(
            f"/api/v1/applications/{application_id}", headers=lawyer_token
        )

        assert response.status_code == 204
        assert not stored_files[0].exists()

    def test_unassigned_lawyer_cannot_read_extracted_fields(
        self, client, lawyer_token, other_lawyer_token, application_id
    ):
        uploaded = _upload(client, lawyer_token, app_id=application_id).json()

        response = client.get(
            f"/api/v1/source-documents/{uploaded['id']}/fields",
            headers=other_lawyer_token,
        )

        assert response.status_code == 403
