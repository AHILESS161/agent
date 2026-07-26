"""Регрессии, найденные при опытной эксплуатации.

Каждый тест закрывает конкретную ошибку, замеченную юристом
на живом стенде.
"""

from __future__ import annotations

import pytest

from app.document_processing.mappers import build_reconciliation
from app.infrastructure.database.models import UserRole
from tests.conftest import login_headers


@pytest.fixture
async def lawyer(client, api_user_factory) -> dict[str, str]:
    await api_user_factory("regress@test.ru", UserRole.lawyer)
    return login_headers(client, "regress@test.ru")


def _intake(client, lawyer, mark: str, **extra) -> dict:
    payload = {
        "create_case": True,
        "new_client": {
            "type": "company",
            "full_name_or_company_name": 'ООО "Пример"',
        },
        "mark_name": mark,
        "mark_text": mark,
    }
    payload.update(extra)
    return client.post("/api/v1/inbound/events", json=payload, headers=lawyer).json()


@pytest.mark.api
class TestEachIntakeCreatesItsOwnCase:
    """Ключ идемпотентности считался только из сопроводительного письма.

    Поля «от кого» и «текст обращения» необязательны и обычно пусты,
    поэтому каждое новое дело выглядело повтором первого — юриста
    возвращало на чужую заявку.
    """

    def test_different_marks_create_different_cases(self, client, lawyer):
        first = _intake(client, lawyer, "ЗВЁЗДОЧКА")
        second = _intake(client, lawyer, "РОМАШКА")

        assert first["created_case_id"] is not None
        assert second["created_case_id"] is not None
        assert first["created_case_id"] != second["created_case_id"]

    def test_second_intake_is_not_marked_duplicate(self, client, lawyer):
        _intake(client, lawyer, "ЗВЁЗДОЧКА")
        second = _intake(client, lawyer, "РОМАШКА")
        assert second.get("is_duplicate") is not True

    def test_explicit_key_still_prevents_double_submit(self, client, lawyer):
        """Двойной клик по одной и той же форме дубля не создаёт."""
        key = "form-session-0001"
        first = _intake(client, lawyer, "ЗВЁЗДОЧКА", idempotency_key=key)
        second = _intake(client, lawyer, "ЗВЁЗДОЧКА", idempotency_key=key)

        assert second["is_duplicate"] is True
        assert second["target_case_id"] == first["created_case_id"]

    def test_same_mark_with_different_keys_creates_two_cases(
        self, client, lawyer
    ):
        """Две заявки на одно обозначение — законный сценарий."""
        first = _intake(client, lawyer, "ЗВЁЗДОЧКА", idempotency_key="a")
        second = _intake(client, lawyer, "ЗВЁЗДОЧКА", idempotency_key="b")
        assert first["created_case_id"] != second["created_case_id"]


class TestIndividualHasPassportFields:
    """Для физлица не было полей паспорта: заполнить их было негде,
    а автоизвлечение из скана требует распознавания текста."""

    def _labels(self, client_type: str) -> set[str]:
        rows, _ = build_reconciliation([], client_type=client_type)
        return {row.label for row in rows}

    def test_passport_fields_are_offered(self):
        labels = self._labels("individual")
        assert any("Паспорт" in label for label in labels)
        assert "Адрес регистрации" in labels

    def test_passport_fields_are_marked_sensitive(self):
        """Персональные данные маскируются в интерфейсе и журналах."""
        rows, _ = build_reconciliation([], client_type="individual")
        passport = [r for r in rows if "Паспорт" in r.label]
        assert passport
        assert all(row.is_sensitive for row in passport)

    def test_passport_fields_can_be_filled_manually(self):
        """Источника в реестрах нет — значит доступен ручной ввод."""
        rows, _ = build_reconciliation([], client_type="individual")
        passport = next(r for r in rows if "серия" in r.label)
        assert "edit" in passport.available_actions

    def test_passport_is_not_shown_to_companies(self):
        assert not any("Паспорт" in label for label in self._labels("company"))

    def test_director_is_not_shown_to_individuals(self):
        """У физического лица руководителя нет."""
        assert not any(
            "руководител" in label.lower() for label in self._labels("individual")
        )


@pytest.mark.api
class TestProfile:
    """Приветствие звучало по фамилии: ФИО хранится как «Фамилия Имя
    Отчество», а бралось первое слово."""

    async def test_preferred_name_can_be_set(self, client, api_user_factory):
        await api_user_factory("profile@test.ru", UserRole.lawyer)
        headers = login_headers(client, "profile@test.ru")

        response = client.patch(
            "/api/v1/auth/me",
            json={"full_name": "Иванова Елена Викторовна", "preferred_name": "Елена"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["preferred_name"] == "Елена"

    async def test_profile_is_returned_by_me(self, client, api_user_factory):
        await api_user_factory("profile2@test.ru", UserRole.lawyer)
        headers = login_headers(client, "profile2@test.ru")
        client.patch(
            "/api/v1/auth/me", json={"preferred_name": "Елена"}, headers=headers
        )

        assert (
            client.get("/api/v1/auth/me", headers=headers).json()["preferred_name"]
            == "Елена"
        )

    async def test_role_cannot_be_changed_through_profile(
        self, client, api_user_factory
    ):
        """Роль — вопрос доступа, а не личных настроек."""
        await api_user_factory("profile3@test.ru", UserRole.lawyer)
        headers = login_headers(client, "profile3@test.ru")

        client.patch(
            "/api/v1/auth/me",
            json={"preferred_name": "Елена", "role": "admin"},
            headers=headers,
        )
        assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "lawyer"

    def test_profile_requires_auth(self, client):
        assert client.patch("/api/v1/auth/me", json={}).status_code == 401
