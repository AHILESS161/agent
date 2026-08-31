"""Расчёт пошлин Роспатента для обычной заявки на товарный знак.

Тарифы вынесены в отдельный модуль и снабжены версией: при изменении
Положения о пошлинах их можно обновить без правок клиентского интерфейса.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import GoodsServicesItem, TrademarkApplicationDraft
from app.services.class_analysis import load_class_context

SOURCE_URL = "https://rospatent.gov.ru/ru/activities/dues/table"
RULES_EFFECTIVE_FROM = "2025-10-04"


def _terms(description: str | None) -> list[str]:
    return [part.strip() for part in re.split(r"[;\n]+", description or "") if part.strip()]


def calculate_amounts(class_count: int, term_surcharge: int = 0) -> dict[str, int]:
    """Посчитать три обязательных платежа по действующей редакции тарифов."""
    if class_count < 1:
        raise ValueError("Для расчёта нужен хотя бы один класс МКТУ")
    extra_classes = max(0, class_count - 1)
    formal = 4000 + extra_classes * 1000
    examination = 13000 + extra_classes * 2500 + term_surcharge
    registration = 18000 + max(0, class_count - 5) * 2000
    return {
        "formal": formal,
        "examination": examination,
        "registration": registration,
        "filing_total": formal + examination,
        "total_electronic": formal + examination + registration,
    }


async def calculate_trademark_fees(
    session: AsyncSession, application_id: int
) -> dict[str, Any]:
    context = await load_class_context(session, application_id)
    application = await session.get(TrademarkApplicationDraft, application_id)
    paper_requested = bool(
        application and application.request_paper_certificate
    )
    selected = context.effective
    class_numbers = sorted({item.class_number for item in selected})

    items = (
        (
            await session.execute(
                select(GoodsServicesItem).where(
                    GoodsServicesItem.application_id == application_id
                )
            )
        )
        .scalars()
        .all()
    )
    item_counts: dict[int, int] = {}
    for item in items:
        number = item.approved_class or item.proposed_class
        item_counts[number] = item_counts.get(number, 0) + 1

    class_details: list[dict[str, int]] = []
    term_surcharge = 0
    for suggestion in selected:
        term_count = item_counts.get(suggestion.class_number)
        if term_count is None:
            term_count = len(_terms(suggestion.class_description))
        extra_terms = max(0, term_count - 10)
        term_surcharge += extra_terms * 500
        class_details.append(
            {
                "class_number": suggestion.class_number,
                "term_count": term_count,
                "extra_terms_over_10": extra_terms,
            }
        )

    class_count = len(class_numbers)
    if not class_count:
        return {
            "application_id": application_id,
            "can_calculate": False,
            "class_count": 0,
            "class_basis": "none",
            "classes": [],
            "payments": [],
            "filing_total": None,
            "registration_total": None,
            "total_electronic": None,
            "paper_certificate_extra": 3000,
            "paper_certificate_requested": paper_requested,
            "total_selected": None,
            "calculated_at": date.today().isoformat(),
            "rules_effective_from": RULES_EFFECTIVE_FROM,
            "source_url": SOURCE_URL,
            "warnings": ["Сначала выберите классы МКТУ — без них пошлину рассчитать нельзя."],
        }

    amounts = calculate_amounts(class_count, term_surcharge)
    formal = amounts["formal"]
    examination = amounts["examination"]
    registration = amounts["registration"]
    filing_total = amounts["filing_total"]

    warnings = [
        "Расчёт не включает льготы, просрочку, изменения заявки и услуги представителей.",
        (
            "В расчёт включено бумажное свидетельство — 3 000 ₽."
            if paper_requested
            else "По умолчанию выдаётся электронное свидетельство. Бумажное можно заказать отдельно за 3 000 ₽."
        ),
    ]
    if not context.is_confirmed:
        warnings.insert(
            0,
            "Расчёт предварительный: использованы предложенные, но ещё не подтверждённые классы.",
        )
    if any(detail["term_count"] == 0 for detail in class_details):
        warnings.append(
            "В некоторых классах перечень товаров и услуг ещё не детализирован; доплата за позиции сверх 10 может измениться."
        )
    if term_surcharge:
        warnings.insert(
            0,
            (
                f"В экспертизу включена доплата {term_surcharge:,} ₽ за наименования "
                "товаров и услуг свыше 10 в одном классе. Сокращение перечня уменьшит "
                "пошлину, но одновременно сузит объём правовой охраны."
            ).replace(",", " "),
        )

    return {
        "application_id": application_id,
        "can_calculate": True,
        "class_count": class_count,
        "class_basis": "confirmed" if context.is_confirmed else "suggested",
        "classes": class_details,
        "payments": [
            {
                "code": "2.1",
                "title": "Регистрация заявки и формальная экспертиза",
                "amount": formal,
                "when": "При подаче заявки",
            },
            {
                "code": "2.4",
                "title": "Экспертиза заявленного обозначения",
                "amount": examination,
                "when": "При подаче заявки",
            },
            {
                "code": "2.11",
                "title": "Регистрация знака и электронное свидетельство",
                "amount": registration,
                "when": "После положительного решения Роспатента",
            },
        ],
        "filing_total": filing_total,
        "registration_total": registration,
        "total_electronic": amounts["total_electronic"],
        "paper_certificate_extra": 3000,
        "paper_certificate_requested": paper_requested,
        "total_selected": amounts["total_electronic"] + (3000 if paper_requested else 0),
        "term_surcharge": term_surcharge,
        "calculated_at": date.today().isoformat(),
        "rules_effective_from": RULES_EFFECTIVE_FROM,
        "source_url": SOURCE_URL,
        "warnings": warnings,
    }
