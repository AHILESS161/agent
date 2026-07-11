"""Common / shared Pydantic schemas."""

from __future__ import annotations

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=200, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic wrapper for paginated list responses."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        total_pages = max(1, (total + page_size - 1) // page_size)
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class HumanReviewTask(BaseModel):
    """Describes a task that requires human review."""

    action: str = Field(description="Action the human should take")
    reason: str = Field(description="Why human review is required")
    urgency: str = Field(default="normal", description="normal / high / critical")


class StructuredAgentOutput(BaseModel):
    """Standardized output format for all AI agent results."""

    model_config = ConfigDict(extra="allow")

    summary: str = Field(description="Brief human-readable summary of findings")
    findings: List[Any] = Field(
        default_factory=list, description="List of individual findings"
    )
    evidence: List[Any] = Field(
        default_factory=list, description="Supporting evidence items"
    )
    missing_info: List[str] = Field(
        default_factory=list,
        description="Fields or documents that are missing and needed",
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score in [0, 1]"
    )
    next_actions: List[str] = Field(
        default_factory=list,
        description="Recommended next actions (for the system or the user)",
    )
    human_review_required: bool = Field(
        default=False,
        description="Whether a human must review before proceeding",
    )
    human_review_tasks: Optional[List[HumanReviewTask]] = Field(
        default=None,
        description="Specific human review tasks when human_review_required is True",
    )


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class IDResponse(BaseModel):
    """Response with the ID of a created or updated resource."""

    id: int
