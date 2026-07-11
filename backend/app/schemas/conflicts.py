"""Conflict search Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.database.models import ConflictDecision, SearchJobStatus


class ConflictSearchRequest(BaseModel):
    """Request to initiate a conflict/prior-rights search."""

    application_id: int
    providers: List[str] = Field(
        default=["fips", "tmview"],
        description="List of search providers to query",
    )
    search_strategy: Optional[dict[str, Any]] = Field(
        default=None,
        description="Custom search strategy; if None the system uses defaults",
    )
    force_new: bool = Field(
        default=False, description="Start a new search even if a recent one exists"
    )


class ConflictSearchJobResponse(BaseModel):
    """Status of a conflict search job."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: SearchJobStatus
    provider: Optional[str] = None
    search_strategy_json: Optional[Any] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_results: int
    error_message: Optional[str] = None


class ConflictSearchResultResponse(BaseModel):
    """A single conflict search result."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    search_job_id: int
    application_id: int
    provider: Optional[str] = None
    source_record_id: Optional[str] = None
    matched_mark: Optional[str] = None
    owner: Optional[str] = None
    classes: Optional[Any] = None
    status: Optional[str] = None
    filing_date: Optional[datetime] = None
    registration_date: Optional[datetime] = None
    similarity_score: Optional[float] = None
    phonetic_score: Optional[float] = None
    translit_score: Optional[float] = None
    semantic_score: Optional[float] = None
    visual_score: Optional[float] = None
    conflict_reason: Optional[str] = None
    reviewer_decision: Optional[ConflictDecision] = None


class ConflictSearchResponse(BaseModel):
    """Full conflict search response for an application."""

    application_id: int
    job: ConflictSearchJobResponse
    results: List[ConflictSearchResultResponse] = []
    total_conflicts: int = 0
    total_no_conflicts: int = 0
    total_needs_review: int = 0


class ConflictReviewDecisionRequest(BaseModel):
    """Payload for a lawyer to mark a conflict result."""

    result_id: int
    decision: ConflictDecision
    reason: Optional[str] = None
