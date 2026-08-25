"""Check the configured LLM without printing credentials or user data."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.agents.classification.rag_class_analyzer import RagNiceClassAnalyzer
from app.api.dependencies import _get_llm_provider, close_llm_provider
from app.infrastructure.database.session import AsyncSessionLocal, close_db
from app.infrastructure.llm.base import LLMMessage
from app.infrastructure.rag.store import load_active_chunks


async def _check_plain(provider: object) -> None:
    response = await provider.generate(
        [LLMMessage(role="user", content="Reply with one word: works")],
        temperature=0.0,
        max_tokens=2000,
    )
    print(
        f"status=ok model={response.model} latency_ms={response.latency_ms} "
        f"answer={response.content.strip()[:80]!r}"
    )


async def _check_nice(provider: object) -> None:
    """Run the real Nice-class RAG path on an anonymous synthetic example."""
    async with AsyncSessionLocal() as session:
        chunks = await load_active_chunks(session)

    query = "Ремонтирую мобильные телефоны и компьютеры Ремонт телефонов и компьютеров"
    analyzer = RagNiceClassAnalyzer(provider, chunks)
    retrieved = analyzer._retrieve_class_candidates(query)
    print(
        json.dumps(
            {
                "retrieved": [
                    {
                        "source_id": item.chunk.citation_id,
                        "anchor": item.chunk.anchor,
                        "score": round(item.score, 4),
                    }
                    for item in retrieved
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    outcome = await analyzer.analyse(
        {
            "mark_text": "TEST MARK",
            "business_description": "Ремонтирую мобильные телефоны и компьютеры",
            "goods_services": "Ремонт телефонов и компьютеров",
        }
    )
    print(
        json.dumps(
            {
                "status": "ok" if outcome.is_conclusive else "fallback",
                "reason": outcome.reason,
                "result": outcome.result.model_dump() if outcome.result else None,
                "verification": outcome.verification,
                "sources_count": len(outcome.sources_used),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--nice",
        action="store_true",
        help="run an anonymous structured Nice-classification smoke test",
    )
    args = parser.parse_args()

    provider = _get_llm_provider()
    print(
        f"provider={type(provider).__name__} "
        f"model={getattr(provider, 'model', 'unknown')}"
    )
    try:
        if args.nice:
            await _check_nice(provider)
        else:
            await _check_plain(provider)
    except Exception as exc:  # noqa: BLE001
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        print(
            f"status=error type={type(exc).__name__} "
            f"http_status={status} detail={str(exc)[:500]!r}"
        )
        raise
    finally:
        await close_llm_provider()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
