"""Тесты маскирования персональных данных и секретов в логах.

Система обрабатывает выписки с ФИО, ИНН и паспортными данными.
Логи живут дольше документов, выгружаются и пересылаются, поэтому
их попадание туда — отдельная утечка.

Все значения в тестах синтетические.
"""

from __future__ import annotations

from app.core.logging import mask_sensitive_data


def mask(event: dict) -> dict:
    return mask_sensitive_data(None, "info", event)


class TestSecretKeys:
    def test_password_is_replaced(self):
        assert mask({"password": "SuperSecret123"})["password"] == "***"

    def test_token_is_replaced(self):
        assert mask({"access_token": "eyJhbGciOi.abc.def"})["access_token"] == "***"

    def test_api_key_is_replaced(self):
        assert mask({"api_key": "sk-abcdefghijklmno"})["api_key"] == "***"

    def test_masking_is_case_insensitive(self):
        assert mask({"Password": "secret"})["Password"] == "***"

    def test_nested_secrets_are_replaced(self):
        result = mask({"payload": {"password": "secret", "email": "a@b.ru"}})
        assert result["payload"]["password"] == "***"


class TestPersonalData:
    def test_individual_inn_is_partially_masked(self):
        result = mask({"event": "ИНН 500100732259 обработан"})
        assert "500100732259" not in result["event"]
        assert "59" in result["event"]

    def test_snils_is_masked(self):
        result = mask({"event": "СНИЛС 999-888-777 66"})
        assert "999-888-777" not in result["event"]

    def test_passport_is_masked(self):
        result = mask({"event": "Паспорт 5544 № 333222"})
        assert "333222" not in result["event"]

    def test_email_local_part_is_masked(self):
        result = mask({"event": "Письмо от IvanovIvan@mail.ru"})
        assert "IvanovIvan" not in result["event"]
        # Домен оставляем: он полезен для диагностики и не идентифицирует лицо.
        assert "mail.ru" in result["event"]

    def test_bearer_token_in_text_is_masked(self):
        result = mask({"event": "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"})
        assert "eyJhbGciOiJIUzI1NiJ9" not in result["event"]


class TestUsefulDataSurvives:
    """Маскирование не должно делать логи бесполезными."""

    def test_company_inn_is_not_masked(self):
        """ИНН юридического лица — 10 цифр, публичный реквизит."""
        result = mask({"event": "ИНН 7707083893"})
        assert "7707083893" in result["event"]

    def test_ogrn_is_not_masked(self):
        result = mask({"event": "ОГРН 1027700132195"})
        assert "1027700132195" in result["event"]

    def test_identifiers_survive(self):
        result = mask({"document_id": 42, "application_id": 7, "request_id": "abc-123"})
        assert result["document_id"] == 42
        assert result["application_id"] == 7
        assert result["request_id"] == "abc-123"

    def test_plain_message_is_unchanged(self):
        result = mask({"event": "Документ загружен, страниц: 10"})
        assert result["event"] == "Документ загружен, страниц: 10"

    def test_non_string_values_are_untouched(self):
        result = mask({"count": 5, "ok": True, "ratio": 0.95})
        assert result == {"count": 5, "ok": True, "ratio": 0.95}
