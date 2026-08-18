from __future__ import annotations

import pytest

from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


class FakeOfficeActionLLM:
    MODEL_NAME = "test-office-action"
    messages = []

    async def generate_structured(self, messages, output_schema, temperature=0.1):
        self.messages = messages
        return {
            "missing_evidence": ["Добавьте каталог продукции"],
            # Даже если провайдер нарушит схему и добавит выдуманный текст,
            # фактическая часть письма не должна использовать его.
            "draft_text": "Продажи осуществлялись в Беларуси с августа 2022 года.",
        }


@pytest.fixture
async def lawyer_headers(client, api_user_factory):
    await api_user_factory("office-lawyer@test.ru", UserRole.lawyer)
    return login_headers(client, "office-lawyer@test.ru")


@pytest.fixture
def application_id(client, lawyer_headers):
    owner = client.post(
        "/api/v1/clients",
        json={"type": "company", "full_name_or_company_name": "ООО Ответ"},
        headers=lawyer_headers,
    ).json()
    return client.post(
        "/api/v1/applications",
        json={"client_id": owner["id"], "mark_name": "ОТВЕТ", "goods_services_raw": "одежда"},
        headers=lawyer_headers,
    ).json()["id"]


def upload_text(client, headers, application_id, name, text):
    response = client.post(
        f"/api/v1/applications/{application_id}/source-documents",
        files={"file": (name, text.encode("utf-8"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.api
def test_office_action_keeps_confirmed_facts_and_generates_docx(
    client, lawyer_headers, application_id, monkeypatch
):
    notice = upload_text(
        client,
        lawyer_headers,
        application_id,
        "уведомление.txt",
        "Необходимо представить пояснения об однородности товаров.",
    )
    proof = upload_text(
        client, lawyer_headers, application_id, "каталог.txt", "Товар продаётся специализированным магазинам."
    )
    created = client.post(
        f"/api/v1/applications/{application_id}/office-actions",
        headers=lawyer_headers,
        json={
            "notice_document_id": notice["id"],
            "homogeneity_facts": [{
                "criterion": "consumers",
                "label": "Покупатели",
                "confirmed": True,
                "fact": "Товар предназначен только для профессиональных покупателей.",
                "document_ids": [proof["id"]],
            }],
            "distinctiveness_evidence": [],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["homogeneity_facts"][0]["fact"].startswith("Товар предназначен")

    fake = FakeOfficeActionLLM()
    monkeypatch.setattr(
        "app.api.v1.endpoints.office_actions.get_llm_provider", lambda: fake
    )
    generated = client.post(
        f"/api/v1/applications/{application_id}/office-actions/{body['id']}/generate",
        headers=lawyer_headers,
    )
    assert generated.status_code == 200
    assert generated.json()["status"] == "generated"
    assert "профессиональных покупателей" in generated.json()["draft_text"]
    assert "Беларуси" not in generated.json()["draft_text"]
    assert "августа 2022" not in generated.json()["draft_text"]
    prompt = fake.messages[-1].content
    assert "профессиональных покупателей" in prompt
    assert "каталог.txt" in prompt

    download = client.get(
        f"/api/v1/applications/{application_id}/office-actions/{body['id']}/download",
        headers=lawyer_headers,
    )
    assert download.status_code == 200
    assert download.content.startswith(b"PK")


@pytest.mark.api
def test_confirmed_checkbox_requires_a_concrete_fact(client, lawyer_headers, application_id):
    notice = upload_text(client, lawyer_headers, application_id, "notice.txt", "Текст")
    response = client.post(
        f"/api/v1/applications/{application_id}/office-actions",
        headers=lawyer_headers,
        json={
            "notice_document_id": notice["id"],
            "homogeneity_facts": [{
                "criterion": "purpose", "label": "Назначение", "confirmed": True,
                "fact": "", "document_ids": [],
            }],
            "distinctiveness_evidence": [],
        },
    )
    assert response.status_code == 422


@pytest.mark.api
def test_rejects_evidence_from_another_application(client, lawyer_headers, application_id):
    notice = upload_text(client, lawyer_headers, application_id, "notice.txt", "Текст")
    response = client.post(
        f"/api/v1/applications/{application_id}/office-actions",
        headers=lawyer_headers,
        json={
            "notice_document_id": notice["id"],
            "homogeneity_facts": [{
                "criterion": "purpose", "label": "Назначение", "confirmed": True,
                "fact": "Факт", "document_ids": [999999],
            }],
            "distinctiveness_evidence": [],
        },
    )
    assert response.status_code == 422
