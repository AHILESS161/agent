"""
ConflictSearchQueryBuilderAgent — builds search queries for finding
conflicting trademark registrations.
"""
from __future__ import annotations

import logging

from app.agents.base import BaseAgent, StructuredAgentOutput

logger = logging.getLogger(__name__)


class ConflictSearchQueryBuilderAgent(BaseAgent):
    """
    Generates comprehensive search queries for conflict checking.

    Produces: exact, fuzzy, phonetic, transliteration, semantic query variants.

    Input dict keys:
        mark_text (str)
        mark_type (str)
        classes (list[int])
        mark_language (str, optional)
        search_depth (str, optional): 'minimal'|'standard'|'comprehensive'

    Output findings:
        queries (list), suggested_classes, search_strategy, total_queries
    """

    agent_type = "conflicts.query_builder"

    input_schema = {
        "type": "object",
        "required": ["mark_text", "mark_type", "classes"],
        "properties": {
            "mark_text": {"type": "string"},
            "mark_type": {"type": "string"},
            "classes": {"type": "array", "items": {"type": "integer"}},
            "mark_language": {"type": "string"},
            "search_depth": {
                "type": "string",
                "enum": ["minimal", "standard", "comprehensive"],
            },
        },
    }

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        variables = {
            "mark_text": input_data.get("mark_text", ""),
            "mark_type": input_data.get("mark_type", "словесное"),
            "classes": input_data.get("classes", []),
        }
        if "mark_language" in input_data:
            variables["mark_language"] = input_data["mark_language"]
        if "search_depth" in input_data:
            variables["search_depth"] = input_data["search_depth"]

        try:
            llm_result = await self._call_llm_structured(
                "conflicts.search_query_builder", variables
            )
        except Exception as exc:
            logger.error("ConflictSearchQueryBuilderAgent LLM call failed: %s", exc)
            # Fallback: generate basic exact query only
            mark_text = input_data.get("mark_text", "")
            llm_result = {
                "queries": [
                    {
                        "type": "exact",
                        "value": mark_text.upper(),
                        "description": "Точное совпадение (fallback)",
                        "confidence": 1.0,
                    }
                ],
                "suggested_classes": input_data.get("classes", []),
                "search_strategy": "minimal",
                "total_queries": 1,
            }

        queries = llm_result.get("queries", [])
        total = llm_result.get("total_queries", len(queries))
        strategy = llm_result.get("search_strategy", "standard")

        summary = (
            f"Сформировано {total} поисковых запросов. "
            f"Стратегия: {strategy}. "
            f"Типы: {', '.join(set(q.get('type','') for q in queries))}."
        )

        return StructuredAgentOutput(
            summary=summary,
            findings=llm_result,
            confidence=0.92,
            next_actions=["execute_conflict_search"],
        )
