from __future__ import annotations

import pytest

from app.services.class_narrowing import (
    InvalidNarrowingResult,
    narrow_class_items,
    validate_official_items,
)


class FakeProvider:
    def __init__(self, result):
        self.result = result

    async def generate_structured(self, **_kwargs):
        return self.result


@pytest.mark.asyncio
async def test_model_can_only_select_exact_official_positions():
    candidates = (
        "установка и ремонт компьютеров",
        "ремонт холодильников",
        "строительство зданий",
    )
    result = await narrow_class_items(
        FakeProvider(
            {
                "selected_indices": [1],
                "rationale": "Заявитель ремонтирует компьютеры.",
                "assumptions": [],
            }
        ),
        class_number=37,
        business_description="Ремонтируем компьютеры",
        goods_services="ремонт компьютеров",
        candidates=candidates,
    )
    assert result.selected_items == ("установка и ремонт компьютеров",)


@pytest.mark.asyncio
async def test_out_of_catalogue_index_is_rejected():
    with pytest.raises(InvalidNarrowingResult):
        await narrow_class_items(
            FakeProvider(
                {
                    "selected_indices": [99],
                    "rationale": "",
                    "assumptions": [],
                }
            ),
            class_number=37,
            business_description="Ремонтируем компьютеры",
            goods_services="",
            candidates=("ремонт компьютеров",),
        )


def test_apply_rejects_invented_wording():
    with pytest.raises(InvalidNarrowingResult):
        validate_official_items(
            ["лучший ремонт компьютеров"],
            ("ремонт компьютеров", "ремонт телефонов"),
        )


def test_apply_keeps_official_order_from_confirmed_preview():
    assert validate_official_items(
        ["ремонт телефонов", "ремонт компьютеров", "ремонт телефонов"],
        ("ремонт компьютеров", "ремонт телефонов"),
    ) == ("ремонт телефонов", "ремонт компьютеров")
