# RAG (Retrieval-Augmented Generation) infrastructure package.
#
# MVP: BM25 / TF-IDF in-memory ranking.
# Production upgrade path: pgvector or Qdrant via drop-in swap of the
# KnowledgePipeline backend without changing any caller code.
#
# Public surface:
#   from app.infrastructure.rag.pipeline import KnowledgePipeline, RetrievalResult
#   from app.infrastructure.rag.knowledge_loader import KnowledgeLoader
