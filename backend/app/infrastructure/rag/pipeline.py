"""
RAG Pipeline — ingestion and retrieval for the Trademark Registration System.

MVP implementation uses a pure-Python BM25 ranking algorithm (no external
vector database required). The interface is designed so that the retrieval
backend can be swapped to pgvector or Qdrant without changing any caller code.

Architecture:
    KnowledgePipeline
    ├── ingest(source_path, source_type, metadata)
    │     └── chunk_text → stores KnowledgeEntry objects in _store
    └── retrieve(query, top_k, filters) → list[RetrievalResult]
          └── _bm25_score(query_tokens, entry_tokens)

Upgrade path to production vector store:
    1. Replace _store (list[KnowledgeEntry]) with Qdrant/pgvector client
    2. Replace _bm25_score with cosine similarity over embeddings
    3. KnowledgePipeline.retrieve() signature stays identical
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeEntry:
    """A single document chunk stored in the pipeline."""

    source_id: str           # Unique identifier for the source document
    chunk_index: int         # Position of this chunk within the source
    content: str             # Raw text of the chunk
    metadata: dict[str, Any] = field(default_factory=dict)

    # Tokenised form stored at ingest time for BM25 efficiency
    tokens: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = _tokenize(self.content)


@dataclass
class RetrievalResult:
    """A single result returned by KnowledgePipeline.retrieve()."""

    content: str
    source_id: str
    chunk_index: int
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        preview = self.content[:80].replace("\n", " ")
        return (
            f"RetrievalResult(source_id={self.source_id!r}, "
            f"chunk={self.chunk_index}, score={self.score:.3f}, "
            f"preview={preview!r})"
        )


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_STOPWORDS_RU = frozenset(
    "и в на с по к о за из не от до но а это как то так же".split()
)


def _tokenize(text: str) -> list[str]:
    """
    Simple whitespace + punctuation tokeniser for Russian/English text.
    Lowercases, removes punctuation, strips stop words.
    """
    tokens = re.findall(r"[а-яёa-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS_RU and len(t) > 1]


# ---------------------------------------------------------------------------
# BM25 scoring
# ---------------------------------------------------------------------------

# BM25 hyperparameters (well-established defaults)
_BM25_K1 = 1.5   # term frequency saturation
_BM25_B = 0.75   # length normalisation


def _bm25_score(
    query_tokens: list[str],
    entry_tokens: list[str],
    avg_doc_len: float,
    idf: dict[str, float],
) -> float:
    """
    Compute BM25 relevance score between a query and a document chunk.

    Args:
        query_tokens: Tokenised query.
        entry_tokens: Tokenised document chunk.
        avg_doc_len: Average document length across the corpus.
        idf: Pre-computed IDF values keyed by token.

    Returns:
        BM25 score (higher = more relevant).
    """
    if not query_tokens or not entry_tokens:
        return 0.0

    doc_len = len(entry_tokens)
    tf_counter = Counter(entry_tokens)
    score = 0.0

    for token in query_tokens:
        if token not in idf:
            continue
        tf = tf_counter.get(token, 0)
        tf_norm = (tf * (_BM25_K1 + 1)) / (
            tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * doc_len / max(avg_doc_len, 1))
        )
        score += idf[token] * tf_norm

    return score


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

class KnowledgePipeline:
    """
    Ingests document sources and retrieves relevant chunks via BM25.

    Usage::

        pipeline = KnowledgePipeline()
        pipeline.ingest(
            source_path="knowledge/gk_rf_part4_trademarks.md",
            source_type="regulation",
            metadata={"title": "ГК РФ Часть IV", "jurisdiction": "RU"},
        )
        results = pipeline.retrieve("абсолютные основания отказа", top_k=3)
        for r in results:
            print(r.score, r.content[:120])

    Production upgrade::

        Subclass or replace this class with a vector-store-backed implementation
        that exposes the same ingest/retrieve interface. No caller changes required.
    """

    def __init__(self) -> None:
        self._store: list[KnowledgeEntry] = []
        # IDF cache — rebuilt lazily when new documents are ingested
        self._idf_cache: dict[str, float] = {}
        self._idf_dirty: bool = True

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(
        self,
        source_path: str,
        source_type: str = "document",
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Read a file, split it into chunks, and store them.

        Args:
            source_path: Path to the source file (or raw text if starts with "text://").
            source_type: Semantic type tag (e.g. "regulation", "guideline", "faq").
            metadata: Arbitrary key-value metadata attached to every chunk.

        Returns:
            source_id: A stable identifier derived from the file path.
        """
        if metadata is None:
            metadata = {}

        # Support inline text injection for testing
        if source_path.startswith("text://"):
            text = source_path[len("text://"):]
            source_id = "inline_" + hashlib.md5(text.encode()).hexdigest()[:8]
        else:
            path = Path(source_path)
            if not path.exists():
                logger.warning(f"RAG ingest: file not found — {source_path}")
                return ""
            text = path.read_text(encoding="utf-8")
            source_id = _stable_source_id(source_path)

        meta = {
            "source_path": source_path,
            "source_type": source_type,
            **metadata,
        }

        chunks = self.chunk_text(text)
        logger.info(
            f"RAG ingest: {source_path!r} → {len(chunks)} chunks "
            f"(source_id={source_id})"
        )

        # Remove existing entries for this source (re-ingest)
        self._store = [e for e in self._store if e.source_id != source_id]

        for idx, chunk in enumerate(chunks):
            entry = KnowledgeEntry(
                source_id=source_id,
                chunk_index=idx,
                content=chunk,
                metadata=meta,
            )
            self._store.append(entry)

        self._idf_dirty = True
        return source_id

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> list[str]:
        """
        Split text into overlapping chunks of approximately `chunk_size` characters.

        Strategy:
        1. Try to split on double newlines (paragraph boundaries) first.
        2. If a paragraph is too long, split on single newlines.
        3. If still too long, split by character count with `overlap`.

        Args:
            text: Input text.
            chunk_size: Target maximum characters per chunk.
            overlap: Characters of overlap between consecutive chunks.

        Returns:
            List of text chunks.
        """
        if not text.strip():
            return []

        # Step 1: split on paragraph breaks
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        chunks: list[str] = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 <= chunk_size:
                current = f"{current}\n\n{para}".strip()
            else:
                if current:
                    chunks.extend(self._hard_split(current, chunk_size, overlap))
                current = para

        if current:
            chunks.extend(self._hard_split(current, chunk_size, overlap))

        return [c.strip() for c in chunks if c.strip()]

    @staticmethod
    def _hard_split(text: str, chunk_size: int, overlap: int) -> list[str]:
        """Split a single block by character count when it exceeds chunk_size."""
        if len(text) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start = end - overlap
        return chunks

    # ------------------------------------------------------------------
    # IDF computation
    # ------------------------------------------------------------------

    def _rebuild_idf(self) -> None:
        """Recompute inverse document frequencies over the current store."""
        N = len(self._store)
        if N == 0:
            self._idf_cache = {}
            self._idf_dirty = False
            return

        df: dict[str, int] = defaultdict(int)
        for entry in self._store:
            for token in set(entry.tokens):
                df[token] += 1

        self._idf_cache = {
            token: math.log((N - count + 0.5) / (count + 0.5) + 1)
            for token, count in df.items()
        }
        self._idf_dirty = False

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[RetrievalResult]:
        """
        Retrieve the most relevant chunks for a query using BM25.

        Args:
            query: Natural language query (Russian or English).
            top_k: Maximum number of results to return.
            filters: Optional metadata filters, e.g. {"source_type": "regulation"}.

        Returns:
            List of RetrievalResult sorted by descending relevance score.
        """
        if not self._store:
            return []

        if self._idf_dirty:
            self._rebuild_idf()

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        # Apply metadata filters
        candidates = self._apply_filters(filters)
        if not candidates:
            return []

        avg_doc_len = sum(len(e.tokens) for e in candidates) / len(candidates)

        scored: list[tuple[float, KnowledgeEntry]] = []
        for entry in candidates:
            score = _bm25_score(
                query_tokens, entry.tokens, avg_doc_len, self._idf_cache
            )
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            RetrievalResult(
                content=entry.content,
                source_id=entry.source_id,
                chunk_index=entry.chunk_index,
                score=round(score, 4),
                metadata=entry.metadata,
            )
            for score, entry in scored[:top_k]
        ]

    def _apply_filters(
        self, filters: Optional[dict[str, Any]]
    ) -> list[KnowledgeEntry]:
        """Return entries that match all provided metadata filters."""
        if not filters:
            return list(self._store)
        result = []
        for entry in self._store:
            if all(entry.metadata.get(k) == v for k, v in filters.items()):
                result.append(entry)
        return result

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @property
    def total_chunks(self) -> int:
        """Total number of chunks currently stored."""
        return len(self._store)

    @property
    def source_ids(self) -> list[str]:
        """Unique source IDs currently in the store."""
        return list({e.source_id for e in self._store})

    def clear(self) -> None:
        """Remove all stored chunks (e.g. between tests)."""
        self._store.clear()
        self._idf_cache.clear()
        self._idf_dirty = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stable_source_id(source_path: str) -> str:
    """Return a stable, filesystem-safe source ID from a file path."""
    name = Path(source_path).stem  # filename without extension
    # Keep only alphanumeric and underscores
    safe = re.sub(r"[^a-zA-Z0-9_а-яёА-ЯЁ]", "_", name)
    return safe[:64]


# ---------------------------------------------------------------------------
# Singleton accessor (optional convenience)
# ---------------------------------------------------------------------------

_default_pipeline: Optional[KnowledgePipeline] = None


def get_pipeline() -> KnowledgePipeline:
    """Return the application-level default pipeline (lazy singleton)."""
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = KnowledgePipeline()
    return _default_pipeline
