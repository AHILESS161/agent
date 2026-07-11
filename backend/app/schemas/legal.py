"""Legal review Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.database.models import (
    FindingSeverity,
    FindingType,
    ReviewerDecision,
    ReviewType,
    RiskLevel,
)


class LegalFindingResponse(BaseModel):
    """Single legal finding."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    legal_review_id: int
    finding_type: FindingType
    ground_article: Optional[str] = None
    description: str
    severity: FindingSeverity
    confidence: Optional[float] = None
    evidence: Optional[str] = None
    source_reference: Optional[str] = None
    recommendation: Optional[str] = None


class LegalReviewRequest(BaseModel):
    """Payload to request a legal review for an application."""

    application_id: int
    review_type: ReviewType = ReviewType.combined
    force_refresh: bool = Field(
        default=False, description="Re-run even if a recent review exists"
    )


class LegalReviewResponse(BaseModel):
    """Full legal review result."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    review_type: ReviewType
    absolute_grounds_summary: Optional[str] = None
    relative_grounds_summary: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    confidence_score: Optional[float] = None
    evidence_json: Optional[Any] = None
    citations_json: Optional[Any] = None
    reviewer_id: Optional[int] = None
    reviewer_decision: Optional[ReviewerDecision] = None
    override_reason: Optional[str] = None
    created_at: datetime
    findings: List[LegalFindingResponse] = []


class LegalReviewDecisionRequest(BaseModel):
    """Payload for a lawyer to record their decision on a legal review."""

    reviewer_decision: ReviewerDecision
    override_reason: Optional[str] = Field(
        default=None,
        description="Required when decision is 'modify' or 'reject'",
    )
