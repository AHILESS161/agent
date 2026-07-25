"""Тесты проверки цитат — защиты от выдуманных источников.

Смысл: RAG нужен не только чтобы дать модели контекст, но и чтобы
каждый вывод можно было проверить. Слабая модель охотно сочиняет
правдоподобные ссылки на несуществующие нормы.
"""

from __future__ import annotations

import pytest

from app.infrastructure.rag.citations import (
    CitationStatus,
    check_citation,
    verify_all,
    verify_quote,
)

SOURCE = (
    "Не допускается государственная регистрация в качестве товарных знаков "
    "обозначений, не обладающих различительной способностью или состоящих "
    "только из элементов, вошедших во всеобщее употребление для обозначения "
    "товаров определённого вида."
)
SOURCES = {"kb-1": SOURCE}


class TestQuoteVerification:
    def test_exact_quote_is_verified(self):
        status, ratio = verify_quote(
            "Не допускается государственная регистрация в качестве товарных знаков",
            SOURCE,
        )
        assert status is CitationStatus.verified
        assert ratio == 1.0

    def test_case_and_yo_differences_are_tolerated(self):
        """Различия регистра и «е/ё» не должны ломать проверку."""
        status, _ = verify_quote(
            "НЕ ДОПУСКАЕТСЯ ГОСУДАРСТВЕННАЯ РЕГИСТРАЦИЯ В КАЧЕСТВЕ ТОВАРНЫХ ЗНАКОВ",
            SOURCE,
        )
        assert status is CitationStatus.verified

    def test_punctuation_differences_are_tolerated(self):
        status, _ = verify_quote(
            "обозначений не обладающих различительной способностью",
            SOURCE,
        )
        assert status in (CitationStatus.verified, CitationStatus.partial)

    def test_fabricated_norm_is_rejected(self):
        """Ключевая проверка: выдуманная норма не проходит."""
        status, ratio = verify_quote(
            "Заявитель обязан уплатить пошлину в размере 50000 рублей "
            "до подачи заявки в Роспатент",
            SOURCE,
        )
        assert status is CitationStatus.not_found
        assert ratio < 0.5

    def test_partially_invented_quote_is_rejected(self):
        """Правдоподобная смесь реального и выдуманного."""
        status, _ = verify_quote(
            "Не допускается регистрация обозначений, если заявитель "
            "не представил нотариально заверенное согласие правообладателя",
            SOURCE,
        )
        assert status is CitationStatus.not_found

    def test_too_short_quote_cannot_confirm_anything(self):
        """Два-три слова найдутся в любом тексте."""
        status, _ = verify_quote("не допускается", SOURCE)
        assert status is CitationStatus.too_short


class TestSourceExistence:
    def test_reference_to_unknown_source_is_rejected(self):
        """Модель не могла видеть источник, которого ей не давали."""
        check = check_citation(
            quote="Не допускается государственная регистрация обозначений",
            source_id="kb-999",
            available_sources=SOURCES,
        )
        assert check.status is CitationStatus.source_missing
        assert not check.is_trustworthy

    def test_missing_source_id_is_rejected(self):
        check = check_citation(
            quote="Не допускается государственная регистрация обозначений",
            source_id=None,
            available_sources=SOURCES,
        )
        assert check.status is CitationStatus.source_missing


class TestVerificationReport:
    def test_report_separates_verified_and_rejected(self):
        report = verify_all(
            [
                {"quote": "Не допускается государственная регистрация в качестве товарных знаков", "source_id": "kb-1"},
                {"quote": "Пошлина составляет 50000 рублей за каждый класс МКТУ", "source_id": "kb-1"},
            ],
            SOURCES,
        )
        assert len(report.verified) == 1
        assert len(report.rejected) == 1

    def test_finding_without_any_valid_citation_is_not_trustworthy(self):
        report = verify_all(
            [{"quote": "Полностью выдуманное положение закона о пошлинах", "source_id": "kb-1"}],
            SOURCES,
        )
        assert report.has_any_trustworthy_source is False

    def test_empty_citations_are_not_trustworthy(self):
        """Вывод вообще без цитат не может считаться обоснованным."""
        report = verify_all([], SOURCES)
        assert report.has_any_trustworthy_source is False

    def test_summary_explains_rejection(self):
        report = verify_all(
            [{"quote": "Выдуманное положение о размере государственной пошлины", "source_id": "kb-1"}],
            SOURCES,
        )
        summary = report.summary()
        assert summary["rejected"] == 1
        assert summary["rejected_reasons"][0]["status"] == "not_found"
