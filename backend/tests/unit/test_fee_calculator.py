"""Тарифы пошлин за обычную заявку на товарный знак."""

import pytest

from app.infrastructure.database.models import (
    ApplicationStatus,
    Client,
    ClientType,
    GoodsServicesItem,
    ItemSource,
    NiceClassSuggestion,
    TrademarkApplicationDraft,
)
from app.services.fee_calculator import calculate_amounts, calculate_trademark_fees


def test_one_class_has_base_fees_only():
    result = calculate_amounts(1)
    assert result == {
        "formal": 4000,
        "examination": 13000,
        "registration": 18000,
        "filing_total": 17000,
        "total_electronic": 35000,
    }


def test_each_class_over_first_increases_both_filing_payments():
    result = calculate_amounts(2)
    assert result["formal"] == 5000
    assert result["examination"] == 15500
    assert result["filing_total"] == 20500
    assert result["total_electronic"] == 38500


def test_registration_increases_only_after_five_classes():
    result = calculate_amounts(6)
    assert result["registration"] == 20000


def test_term_surcharge_is_added_to_examination():
    result = calculate_amounts(1, term_surcharge=1500)
    assert result["examination"] == 14500
    assert result["total_electronic"] == 36500


def test_zero_classes_cannot_be_calculated():
    with pytest.raises(ValueError):
        calculate_amounts(0)


async def test_narrowed_class_description_overrides_stale_extracted_items(async_session):
    client = Client(type=ClientType.company, full_name_or_company_name='ООО "Игрушки"')
    async_session.add(client)
    await async_session.flush()
    application = TrademarkApplicationDraft(
        client_id=client.id,
        mark_name="ЗВЁЗДОЧКА",
        status=ApplicationStatus.draft,
    )
    async_session.add(application)
    await async_session.flush()
    async_session.add(
        NiceClassSuggestion(
            application_id=application.id,
            class_number=35,
            class_description="услуги магазинов игрушек; услуги интернет-магазинов игрушек",
            approved=True,
        )
    )
    # These rows represent an earlier full-catalogue extraction.  They must
    # not keep the surcharge alive after the confirmed wording was narrowed.
    async_session.add_all(
        GoodsServicesItem(
            application_id=application.id,
            raw_text=f"старая позиция {index}",
            proposed_class=35,
            source=ItemSource.ai,
        )
        for index in range(20)
    )
    await async_session.flush()

    result = await calculate_trademark_fees(async_session, application.id)

    assert result["classes"] == [
        {"class_number": 35, "term_count": 2, "extra_terms_over_10": 0}
    ]
    assert result["term_surcharge"] == 0
