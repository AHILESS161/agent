"""Stateless designation choice using the configured, budgeted LLM provider."""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.infrastructure.llm.base import BaseLLMProvider, LLMMessage
from app.infrastructure.llm.fallback_provider import FallbackLLMProvider
from app.infrastructure.llm.mock_provider import MockLLMProvider
from app.infrastructure.llm.prompt_registry import PromptRegistry
from app.schemas.mark_comparison import (
    CandidateAssessment, ComparedCandidate, CompareMarksRequest, CompareMarksResponse,
    ComparisonAssessment, ComparisonSource,
)

logger = get_logger(__name__)
COMPARISON_TIMEOUT_SECONDS = 60.0
LIMITATIONS = [
    "Это предварительная оценка различительной способности и описательности для указанных товаров и услуг.",
    "Поиск по зарегистрированным знакам и поданным заявкам не проводился. Конфликты с правами других лиц не оценены.",
    "Вывод не означает, что обозначение свободно или будет зарегистрировано. Другие основания отказа требуют отдельной проверки.",
]


class ComparisonUnavailable(AppError):
    status_code = 503
    error_code = "comparison_unavailable"


@lru_cache(maxsize=1)
def _comparison_prompts() -> PromptRegistry:
    registry = PromptRegistry()
    registry.load_from_directory(Path(__file__).resolve().parents[2] / "prompts" / "legal")
    return registry


def _contains_mock(provider: BaseLLMProvider) -> bool:
    if isinstance(provider, MockLLMProvider):
        return True
    if isinstance(provider, FallbackLLMProvider):
        return _contains_mock(provider.primary) or _contains_mock(provider.fallback)
    return False


def _demo_assessment(payload: CompareMarksRequest) -> ComparisonAssessment:
    """One explicit teaching fixture, never a dictionary that grades arbitrary inputs."""
    names = (payload.first.casefold(), payload.second.casefold())
    if set(names) != {"яблоневый сад", "я-ко"} or payload.goods.casefold() != "магазин фруктов":
        raise ComparisonUnavailable(
            "В деморежиме доступен только пример «Яблоневый сад» и «Я-ко» для магазина фруктов. "
            "Для сравнения своих обозначений нужен подключённый сервис анализа."
        )
    garden = CandidateAssessment(
        category="suggestive", distinctiveness="moderate", description_risk="medium",
        goods_relation="Вызывает прямую ассоциацию с выращиванием яблок и происхождением фруктов.",
        reasoning="В учебном примере связь с фруктами делает название менее самостоятельным. "
                  "При этом ассоциация с садом сама по себе не доказывает, что название прямо описывает услуги магазина.",
        strengths=["Понятный образ, связанный с ассортиментом."],
        risks=["Связь с фруктами может ослаблять различительную способность; требуется оценка полного перечня товаров и услуг."],
    )
    yako = CandidateAssessment(
        category="fanciful", distinctiveness="strong", description_risk="low",
        goods_relation="В условиях учебного примера обозначение не описывает фрукты или услуги их продажи.",
        reasoning="Если у «Я-ко» нет описательного значения для выбранных товаров и услуг, "
                  "такое созданное название способно лучше выделять магазин. Значение и восприятие нужно проверить отдельно.",
        strengths=["В примере предполагается самостоятельное созданное название без прямого описания ассортимента."],
        risks=["Предположение о фантазийности требует проверки значения и восприятия.",
               "Даже фантазийное название может конфликтовать с более ранними знаками."],
    )
    return ComparisonAssessment(
        recommended="first" if names[0] == "я-ко" else "second",
        summary="Учебный пример: при условии, что «Я-ко» не имеет описательного значения, "
                "его стоит рассмотреть в первую очередь по различительной способности для магазина фруктов. "
                "Это заранее подготовленный разбор, а не анализ введённых данных моделью.",
        first=yako if names[0] == "я-ко" else garden,
        second=yako if names[1] == "я-ко" else garden,
        next_steps=["Уточнить товары и услуги: продажа фруктов, сами фрукты или оба направления.",
                    "Проверить значение «Я-ко» и восприятие обоих названий потребителями.",
                    "Провести поиск по более ранним знакам и заявкам перед подачей."],
    )


async def compare_marks(payload: CompareMarksRequest, provider: BaseLLMProvider) -> CompareMarksResponse:
    demo = settings.DEMO_MODE or _contains_mock(provider)
    if demo:
        assessment = _demo_assessment(payload)
    else:
        try:
            registry = _comparison_prompts()
            messages = [LLMMessage(**message) for message in registry.build_messages(
                "legal.mark_choice", {"input_json": json.dumps(payload.model_dump(), ensure_ascii=False)}
            )]
            raw = await asyncio.wait_for(provider.generate_structured(
                messages, output_schema=ComparisonAssessment.model_json_schema(), temperature=0.1,
            ), timeout=COMPARISON_TIMEOUT_SECONDS)
            assessment = ComparisonAssessment.model_validate(raw)
        except HTTPException as exc:
            if exc.status_code == 429:
                raise
            logger.warning("mark_comparison_unavailable", error=type(exc).__name__)
            raise ComparisonUnavailable("Сейчас не удалось сравнить обозначения. Попробуйте позже.") from None
        except Exception as exc:
            # Do not log provider messages, payloads or validation errors containing user data.
            logger.warning("mark_comparison_unavailable", error=type(exc).__name__)
            raise ComparisonUnavailable("Сейчас не удалось сравнить обозначения. Попробуйте позже.") from None
    return CompareMarksResponse(
        mode="demo" if demo else "analysis",
        recommended=assessment.recommended, summary=assessment.summary,
        first=ComparedCandidate(designation=payload.first, **assessment.first.model_dump()),
        second=ComparedCandidate(designation=payload.second, **assessment.second.model_dump()),
        next_steps=assessment.next_steps,
        limitations=(["Демонстрационный пример: реальная модель анализа не вызывалась."] if demo else []) + LIMITATIONS,
        registry_checked=False,
        sources=[
            ComparisonSource(
                title="ГК РФ, статья 1483, пункты 1 и 1.1",
                url="https://rospatent.gov.ru/ru/documents/grazhdanskiy-kodeks-rossiyskoy-federacii-chast-chetvertaya",
            ),
            ComparisonSource(
                title="ВОИС: товарные знаки для бизнеса, страницы 26–27",
                url="https://rospatent.gov.ru/content/uploadfiles/docs/ip-dlya-biznesa-tz.pdf",
            ),
        ],
    )
