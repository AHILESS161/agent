"""Полный ZIP-пакет для самостоятельной подачи."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import docx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.models import (
    AnalysisKind,
    ApplicationStatus,
    Client,
    ClientType,
    MarkType,
    NiceCategory,
    NiceClassSuggestion,
    RiskAssessment,
    RiskLevel,
    SearchMode,
    TrademarkApplicationDraft,
    UserRole,
)
from tests.conftest import login_headers


@pytest.mark.api
class TestFilingPackage:
    async def test_sound_mark_requires_audio_attachment(self, client, api_user_factory):
        await api_user_factory("filing-sound@test.ru", UserRole.client)
        headers = login_headers(client, "filing-sound@test.ru")
        applicant = client.post(
            "/api/v1/clients",
            json={"type": "individual", "full_name_or_company_name": "Иван Тестов"},
            headers=headers,
        ).json()
        application = client.post(
            "/api/v1/applications",
            json={"client_id": applicant["id"], "mark_name": "ДЖИНГЛ", "mark_type": "sound"},
            headers=headers,
        ).json()

        status = client.get(
            f"/api/v1/applications/{application['id']}/filing-package",
            headers=headers,
        )
        assert status.status_code == 200, status.text
        assert "mark_audio" in {item["code"] for item in status.json()["blockers"]}

    async def test_user_confirms_document_kind_before_packaging(self, client, api_user_factory):
        await api_user_factory("filing-kind@test.ru", UserRole.client)
        headers = login_headers(client, "filing-kind@test.ru")
        applicant = client.post(
            "/api/v1/clients",
            json={"type": "individual", "full_name_or_company_name": "Иван Тестов"},
            headers=headers,
        ).json()
        application = client.post(
            "/api/v1/applications",
            json={"client_id": applicant["id"], "mark_name": "ТЕСТ", "mark_type": "word"},
            headers=headers,
        ).json()
        upload = client.post(
            f"/api/v1/applications/{application['id']}/source-documents",
            files={
                "file": (
                    "doverennost.txt",
                    "ДОВЕРЕННОСТЬ\nНастоящей доверенностью заявитель уполномочивает представителя.",
                    "text/plain",
                )
            },
            headers=headers,
        )
        assert upload.status_code == 201, upload.text
        assert upload.json()["kind_requires_confirmation"] is True

        confirmed = client.put(
            f"/api/v1/source-documents/{upload.json()['id']}/kind",
            json={"document_kind": "power_of_attorney"},
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["document_kind"] == "power_of_attorney"
        assert confirmed.json()["kind_requires_confirmation"] is False

    async def test_incomplete_case_returns_actionable_blockers(self, client, api_user_factory):
        await api_user_factory("filing-blocked@test.ru", UserRole.client)
        headers = login_headers(client, "filing-blocked@test.ru")
        applicant = client.post(
            "/api/v1/clients",
            json={"type": "individual", "full_name_or_company_name": "Иван Тестов"},
            headers=headers,
        ).json()
        application = client.post(
            "/api/v1/applications",
            json={"client_id": applicant["id"], "mark_name": "ТЕСТ", "mark_type": "word"},
            headers=headers,
        ).json()

        status = client.get(
            f"/api/v1/applications/{application['id']}/filing-package",
            headers=headers,
        )
        assert status.status_code == 200
        body = status.json()
        assert body["ready"] is False
        assert body["blockers"]
        assert all({"title", "action", "section"} <= set(item) for item in body["blockers"])

        download = client.get(
            f"/api/v1/applications/{application['id']}/filing-package/download",
            headers=headers,
        )
        assert download.status_code == 409
        assert download.json()["detail"]["blockers"]

    async def test_ready_case_downloads_split_zip(self, client, api_user_factory, async_engine):
        user = await api_user_factory("filing-ready@test.ru", UserRole.client)
        factory = async_sessionmaker(
            bind=async_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session:
            applicant = Client(
                type=ClientType.company,
                full_name_or_company_name='ООО "Готовый пакет"',
                inn="7701234567",
                ogrn_or_ogrnip="1027700123456",
                address="123456, г. Москва, ул. Тестовая, д. 1",
                country="RU",
                email="owner@example.test",
                phone="+7 900 000-00-00",
                created_by_user_id=user.id,
            )
            session.add(applicant)
            await session.flush()
            application = TrademarkApplicationDraft(
                client_id=applicant.id,
                created_by_user_id=user.id,
                status=ApplicationStatus.memo_approved,
                mark_type=MarkType.word,
                mark_name="ГОТОВЫЙ ЗНАК",
                mark_text="ГОТОВЫЙ ЗНАК",
                description_of_mark="Словесное обозначение кириллицей",
                business_description="Разработка программного обеспечения",
                goods_services_raw="Программное обеспечение; разработка программ",
                territory="Российская Федерация",
                filing_method="electronic",
                signatory_name="Иванов Иван Иванович",
                signatory_position="генеральный директор",
                signature_date=date(2026, 8, 26),
            )
            session.add(application)
            await session.flush()
            session.add(
                NiceClassSuggestion(
                    application_id=application.id,
                    class_number=42,
                    class_description="разработка программного обеспечения",
                    rationale="Основной вид деятельности",
                    confidence=0.95,
                    category=NiceCategory.primary,
                    approved=True,
                    approved_by=user.id,
                )
            )
            for kind in (AnalysisKind.absolute_grounds, AnalysisKind.relative_grounds):
                session.add(
                    RiskAssessment(
                        application_id=application.id,
                        analysis_kind=kind,
                        overall_risk=RiskLevel.low,
                        summary="Существенные препятствия в доступном объёме проверки не выявлены.",
                        is_inconclusive=False,
                        search_mode=SearchMode.limited,
                        classes_considered_json=[42],
                        classes_confirmed=True,
                        requires_specialist_review=True,
                    )
                )
            await session.commit()
            application_id = application.id

        headers = login_headers(client, "filing-ready@test.ru")
        status = client.get(
            f"/api/v1/applications/{application_id}/filing-package",
            headers=headers,
        )
        assert status.status_code == 200, status.text
        body = status.json()
        assert body["ready"] is True, body["blockers"]
        assert body["filing_document_count"] == 1
        assert body["reference_document_count"] == 4
        assert body["class_numbers"] == [42]
        assert body["filing_fee"] > 0

        download = client.get(
            f"/api/v1/applications/{application_id}/filing-package/download",
            headers=headers,
        )
        assert download.status_code == 200, download.text
        assert download.headers["content-type"].startswith("application/zip")

        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            names = set(archive.namelist())
            assert "01_ДЛЯ_ПОДАЧИ/01_заявление.docx" in names
            assert "01_ДЛЯ_ПОДАЧИ/02_перечень_товаров_и_услуг.docx" not in names
            assert "02_ДЛЯ_ВАС/01_инструкция_по_подаче.docx" in names
            assert "02_ДЛЯ_ВАС/02_расчёт_пошлин.docx" in names
            assert "02_ДЛЯ_ВАС/03_результат_проверки.docx" in names
            assert "02_ДЛЯ_ВАС/04_контрольный_список.txt" in names
            assert "README.txt" in names

            instruction = docx.Document(
                io.BytesIO(archive.read("02_ДЛЯ_ВАС/01_инструкция_по_подаче.docx"))
            )
            text = "\n".join(paragraph.text for paragraph in instruction.paragraphs)
            assert "не загружайте весь ZIP" in text
            assert "Сохраните подтверждение" in text
