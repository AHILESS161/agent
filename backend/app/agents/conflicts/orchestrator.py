"""
ConflictSearchOrchestrator — calls the registry provider, aggregates results
from multiple query types, deduplicates, and ranks conflicts by relevance.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents.base import BaseAgent, StructuredAgentOutput
from app.infrastructure.providers.base import SearchQuery, TrademarkRegistryProvider

logger = logging.getLogger(__name__)

_SEARCH_TYPES = ["exact", "fuzzy", "phonetic", "transliteration", "semantic"]


def _deduplicate(records: list[dict]) -> list[dict]:
    """Deduplicate by record_id, keeping first occurrence."""
    seen: set[str] = set()
    result: list[dict] = []
    for r in records:
        rid = r.get("record_id", "")
        if rid not in seen:
            seen.add(rid)
            result.append(r)
    return result


def _rank_records(records: list[dict], mark_text: str) -> list[dict]:
    """
    Simple ranking: registered > pending > expired, then alphabetic.
    For a production system, this would use similarity scores.
    """
    STATUS_ORDER = {"registered": 0, "pending": 1, "expired": 2, "cancelled": 3}
    return sorted(
        records,
        key=lambda r: (STATUS_ORDER.get(r.get("status", ""), 9), r.get("mark_text", "")),
    )


class ConflictSearchOrchestrator(BaseAgent):
    """
    Orchestrates conflict searches across all query types.

    Requires a registry provider to be injected.

    Input dict keys:
        queries (list[{type, value}]): from ConflictSearchQueryBuilderAgent
        classes (list[int])
        max_results_per_query (int, optional, default=20)

    Output findings:
        conflicts (list of RegistryRecord dicts), total_found, search_stats
    """

    agent_type = "conflicts.orchestrator"

    input_schema = {
        "type": "object",
        "required": ["queries", "classes"],
        "properties": {
            "queries": {"type": "array"},
            "classes": {"type": "array", "items": {"type": "integer"}},
            "max_results_per_query": {"type": "integer", "default": 20},
        },
    }

    def __init__(self, prompt_registry, llm_provider, registry_provider: TrademarkRegistryProvider):
        super().__init__(prompt_registry, llm_provider)
        self.registry_provider = registry_provider

    async def execute(self, input_data: dict) -> StructuredAgentOutput:
        queries = input_data.get("queries", [])
        classes = input_data.get("classes", [])
        max_results = input_data.get("max_results_per_query", 20)

        all_records: list[dict] = []
        search_stats: dict[str, Any] = {"queries_executed": 0, "results_per_type": {}}

        for query_def in queries:
            search_type = query_def.get("type", "exact")
            value = query_def.get("value", "")
            if not value:
                continue

            sq = SearchQuery(
                mark_text=value,
                classes=classes if classes else None,
                search_type=search_type,
                max_results=max_results,
            )

            try:
                results = await self.registry_provider.search_marks(sq)
                records_dicts = [r.model_dump() for r in results]
                all_records.extend(records_dicts)
                search_stats["queries_executed"] += 1
                search_stats["results_per_type"][search_type] = (
                    search_stats["results_per_type"].get(search_type, 0) + len(results)
                )
                logger.debug(
                    "ConflictSearch | type=%s | query='%s' | found=%d",
                    search_type,
                    value,
                    len(results),
                )
            except Exception as exc:
                logger.warning(
                    "Registry search failed for type=%s query='%s': %s",
                    search_type,
                    value,
                    exc,
                )

        # Also run application search (includes pending)
        if queries:
            first_query = queries[0]
            try:
                app_sq = SearchQuery(
                    mark_text=first_query.get("value", ""),
                    classes=classes if classes else None,
                    search_type="fuzzy",
                    max_results=max_results,
                )
                app_results = await self.registry_provider.search_applications(app_sq)
                all_records.extend([r.model_dump() for r in app_results])
            except Exception as exc:
                logger.warning("Application search failed: %s", exc)

        deduped = _deduplicate(all_records)
        ranked = _rank_records(deduped, queries[0].get("value", "") if queries else "")

        findings = {
            "conflicts": ranked,
            "total_found": len(ranked),
            "search_stats": search_stats,
        }

        summary = (
            f"Поиск конфликтов завершён. "
            f"Запросов выполнено: {search_stats['queries_executed']}. "
            f"Найдено уникальных записей: {len(ranked)}."
        )

        return StructuredAgentOutput(
            summary=summary,
            findings=findings,
            confidence=0.90,
            evidence=[{"record_id": r.get("record_id"), "mark_text": r.get("mark_text")} for r in ranked],
            next_actions=["analyze_conflicts"] if ranked else ["proceed_to_recommendation"],
        )
