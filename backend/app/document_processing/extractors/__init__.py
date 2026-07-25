"""Детерминированные извлекатели полей (regex + правила, без LLM)."""

from app.document_processing.extractors.registry import (
    ExtractedFieldResult,
    FieldCandidateResult,
    RegistryExtractor,
    extract_registry_fields,
)

__all__ = [
    "ExtractedFieldResult",
    "FieldCandidateResult",
    "RegistryExtractor",
    "extract_registry_fields",
]
