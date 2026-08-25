"""Поиск релевантных фрагментов базы знаний.

Ранжирование — BM25 поверх фрагментов из БД. Внешнее векторное
хранилище не требуется: корпус нормативных материалов небольшой,
а лексический поиск по юридическим терминам работает предсказуемо
и объяснимо.

Сигнатура ``retrieve()`` рассчитана на замену бэкенда поиска
на pgvector/Qdrant без изменений в вызывающем коде.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.infrastructure.rag.stemmer import stem
from app.infrastructure.rag.store import StoredChunk

# Параметры BM25.
_K1 = 1.5
_B = 0.75

# Служебные слова русского языка не несут смысловой нагрузки
# и только зашумляют ранжирование.
_STOPWORDS = frozenset(
    """
    и в во не что он на я с со как а то все она так его но да ты к у же вы за
    бы по только ее мне было вот от меня еще нет о из ему теперь когда даже ну
    вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там
    потом себя ничего ей может они тут где есть надо ней для мы тебя их чем
    была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того
    потому этого какой совсем ним здесь этом один почти мой тем чтобы нее были
    куда зачем всех никогда можно при наконец два об другой хоть после над
    больше тот через эти нас про всего них какая много разве три эту моя
    впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более
    всегда конечно всю между
    """.split()
)


def _tokenize(text: str) -> list[str]:
    """Разбить текст на основы слов.

    Стемминг обязателен: русский язык флективен, и без него запрос
    «герб, флаг» не находит норму, где написано «гербами, флагами».
    """
    text = text.lower().replace("ё", "е")
    tokens = re.findall(r"[а-яa-z0-9]+", text)
    return [stem(t) for t in tokens if len(t) > 2 and t not in _STOPWORDS]


@dataclass
class RetrievedChunk:
    """Фрагмент, отобранный для контекста модели."""

    chunk: StoredChunk
    score: float

    @property
    def citation_id(self) -> str:
        return self.chunk.citation_id


class Retriever:
    """BM25-поиск по фрагментам базы знаний."""

    def __init__(self, chunks: list[StoredChunk]) -> None:
        self._chunks = chunks
        self._tokens = [_tokenize(c.content) for c in chunks]
        self._lengths = [len(t) for t in self._tokens]
        self._avg_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )
        self._idf = self._build_idf()

    def _build_idf(self) -> dict[str, float]:
        total = len(self._tokens)
        if not total:
            return {}
        document_frequency: Counter[str] = Counter()
        for tokens in self._tokens:
            document_frequency.update(set(tokens))
        return {
            term: math.log(1 + (total - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def _score(self, query_tokens: list[str], index: int) -> float:
        if not self._tokens[index]:
            return 0.0
        counts = Counter(self._tokens[index])
        length = self._lengths[index]
        score = 0.0
        for term in query_tokens:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            idf = self._idf.get(term, 0.0)
            denominator = frequency + _K1 * (
                1 - _B + _B * length / (self._avg_length or 1)
            )
            score += idf * (frequency * (_K1 + 1)) / denominator
        return score

    def retrieve(
        self,
        query: str,
        top_k: int = 6,
        article: str | None = None,
        min_score: float = 0.1,
    ) -> list[RetrievedChunk]:
        """Найти наиболее релевантные фрагменты.

        ``article`` ограничивает поиск конкретной статьей — полезно,
        когда заранее известно, какое основание проверяется.
        """
        query_tokens = _tokenize(query)
        if not query_tokens or not self._chunks:
            return []

        candidates = [
            (index, chunk)
            for index, chunk in enumerate(self._chunks)
            if article is None or chunk.article == article
        ]

        scored = [
            RetrievedChunk(chunk=chunk, score=self._score(query_tokens, index))
            for index, chunk in candidates
        ]
        scored = [item for item in scored if item.score >= min_score]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]


def build_context(retrieved: list[RetrievedChunk]) -> tuple[str, dict[str, str]]:
    """Собрать текст контекста для модели и карту источников.

    Карта источников нужна для последующей проверки цитат: модель
    может ссылаться только на то, что ей действительно показали.
    """
    blocks: list[str] = []
    sources: dict[str, str] = {}

    for item in retrieved:
        chunk = item.chunk
        sources[item.citation_id] = chunk.content
        provenance = []
        if chunk.source_metadata:
            edition = chunk.source_metadata.get("edition")
            effective_from = chunk.source_metadata.get("effective_from")
            verified_at = chunk.source_metadata.get("verified_at")
            if edition:
                provenance.append(f"редакция: {edition}")
            if effective_from:
                provenance.append(f"действует с: {effective_from}")
            if verified_at:
                provenance.append(f"проверено: {verified_at}")
        if chunk.source_url:
            provenance.append(f"официальный источник: {chunk.source_url}")
        provenance_text = f" [{'; '.join(provenance)}]" if provenance else ""
        blocks.append(
            f"[source_id: {item.citation_id}] "
            f"[{chunk.source_name} — {chunk.anchor}]{provenance_text}\n{chunk.content}"
        )

    return "\n\n---\n\n".join(blocks), sources
