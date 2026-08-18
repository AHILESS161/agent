"""Тесты определения типа документа.

Фикстуры обезличены: реквизиты синтетические, реальные данные из
приложенных к репозиторию документов сюда не копируются.
"""

from __future__ import annotations

from app.document_processing.classifier import classify_document
from app.infrastructure.database.models import DocumentKind

EGRUL_TEXT = """
ВЫПИСКА
из Единого государственного реестра юридических лиц
01.01.2024 № ЮЭ0000-00-00000000
Настоящая выписка содержит сведения о юридическом лице
№ п/п Наименование показателя Значение показателя
1 Полное наименование ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРИМЕР"
2 Сокращенное наименование ООО "ПРИМЕР"
13 ОГРН 1000000000000
14 Дата регистрации 01.01.2020
Сведения о регистрирующем органе по месту нахождения юридического лица
Сведения об уставном капитале
Сведения о лице, имеющем право без доверенности действовать от имени юридического лица
"""

EGRIP_TEXT = """
ВЫПИСКА
из Единого государственного реестра индивидуальных предпринимателей
Сведения об индивидуальном предпринимателе
ОГРНИП 300000000000000
Фамилия ИВАНОВ
"""

APPLICATION_TEXT = """
ЗАЯВКА
на государственную регистрацию товарного знака, знака обслуживания, коллективного знака
В Федеральную службу по интеллектуальной собственности
(731) ЗАЯВИТЕЛЬ
(540) ЗАЯВЛЯЕМОЕ ОБОЗНАЧЕНИЕ
(511) ПЕРЕЧЕНЬ ТОВАРОВ, сгруппированные по классам МКТУ
"""

POA_TEXT = """
ДОВЕРЕННОСТЬ
город Москва, первое января две тысячи двадцать четвёртого года
Настоящей доверенностью уполномочиваю представлять интересы
сроком на три года
"""


class TestKnownTypes:
    def test_recognises_egrul(self):
        result = classify_document(EGRUL_TEXT)
        assert result.kind is DocumentKind.egrul_extract
        assert result.confidence >= 0.7

    def test_recognises_egrip_not_egrul(self):
        """ЕГРИП не должен подменяться ЕГРЮЛ — это разные субъекты."""
        result = classify_document(EGRIP_TEXT)
        assert result.kind is DocumentKind.egrip_extract

    def test_recognises_trademark_application(self):
        result = classify_document(APPLICATION_TEXT)
        assert result.kind is DocumentKind.trademark_application
        assert result.confidence >= 0.7

    def test_recognises_power_of_attorney(self):
        assert classify_document(POA_TEXT).kind is DocumentKind.power_of_attorney

    def test_recognises_passport(self):
        text = (
            "Паспорт гражданина Российской Федерации. Паспорт выдан ОМВД России. "
            "Код подразделения 770-001. Дата рождения 01.01.1990."
        )
        assert classify_document(text).kind is DocumentKind.passport

    def test_reports_matched_markers_for_explainability(self):
        result = classify_document(EGRUL_TEXT)
        assert result.matched_markers
        assert result.reason


class TestUncertainCases:
    def test_empty_text_is_unknown(self):
        result = classify_document("")
        assert result.kind is DocumentKind.unknown
        assert result.confidence == 0.0

    def test_whitespace_only_is_unknown(self):
        assert classify_document("   \n\t  ").kind is DocumentKind.unknown

    def test_unrelated_document_is_unknown(self):
        text = "Договор аренды нежилого помещения. Арендодатель передаёт во временное пользование."
        assert classify_document(text).kind is DocumentKind.unknown

    def test_registry_details_without_header_flagged_for_manual_review(self):
        """Реквизиты есть, заголовок не опознан — тип подменять нельзя."""
        text = "ИНН 1000000000 КПП 100000000 ОГРН 1000000000000 сведения из реестра"
        result = classify_document(text)
        assert result.kind is DocumentKind.unknown_registry_extract
        assert result.requires_confirmation is True
        assert result.confidence < 0.5


class TestHumanInTheLoop:
    def test_every_classification_requires_confirmation(self):
        """Даже уверенное определение типа подтверждает специалист."""
        for text in (EGRUL_TEXT, EGRIP_TEXT, APPLICATION_TEXT, POA_TEXT, ""):
            assert classify_document(text).requires_confirmation is True

    def test_confidence_never_reaches_certainty(self):
        for text in (EGRUL_TEXT, APPLICATION_TEXT):
            assert classify_document(text).confidence < 1.0
