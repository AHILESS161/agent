"""Trademark application draft schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.database.models import ApplicationStatus, MarkType


class ApplicationCreate(BaseModel):
    """Payload for creating a new application draft."""

    client_id: int
    mark_type: Optional[MarkType] = None
    mark_name: Optional[str] = Field(default=None, max_length=255)
    mark_text: Optional[str] = None
    mark_image_file_id: Optional[str] = Field(default=None, max_length=255)
    colors_claimed: Optional[str] = None
    transliteration: Optional[str] = None
    translation: Optional[str] = None
    description_of_mark: Optional[str] = None
    business_description: Optional[str] = None
    goods_services_raw: Optional[str] = None
    territory: Optional[str] = Field(default=None, max_length=255)
    priority_claim: Optional[str] = None
    notes: Optional[str] = None
    assigned_lawyer_id: Optional[int] = None
    assigned_manager_id: Optional[int] = None


class ApplicationUpdate(BaseModel):
    """Payload for partially updating an application draft."""

    mark_type: Optional[MarkType] = None
    mark_name: Optional[str] = Field(default=None, max_length=255)
    mark_text: Optional[str] = None
    mark_image_file_id: Optional[str] = Field(default=None, max_length=255)
    colors_claimed: Optional[str] = None
    transliteration: Optional[str] = None
    translation: Optional[str] = None
    description_of_mark: Optional[str] = None
    business_description: Optional[str] = None
    goods_services_raw: Optional[str] = None
    territory: Optional[str] = Field(default=None, max_length=255)
    priority_claim: Optional[str] = None
    notes: Optional[str] = None
    assigned_lawyer_id: Optional[int] = None
    assigned_manager_id: Optional[int] = None


class ApplicationResponse(BaseModel):
    """Full application draft representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    assigned_lawyer_id: Optional[int] = None
    assigned_manager_id: Optional[int] = None
    status: ApplicationStatus
    mark_type: Optional[MarkType] = None
    mark_name: Optional[str] = None
    mark_text: Optional[str] = None
    mark_image_file_id: Optional[str] = None
    colors_claimed: Optional[str] = None
    transliteration: Optional[str] = None
    translation: Optional[str] = None
    description_of_mark: Optional[str] = None
    business_description: Optional[str] = None
    goods_services_raw: Optional[str] = None
    territory: Optional[str] = None
    priority_claim: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ValidationIssue(BaseModel):
    """A single validation issue found by the completeness engine."""

    field: Optional[str] = None
    message: str
    severity: str  # "blocking" | "non_blocking"
    stage: Optional[str] = None


class ApplicationValidationResult(BaseModel):
    """Result returned by the completeness / validation check."""

    is_complete: bool
    blocking_issues: List[ValidationIssue] = []
    non_blocking_issues: List[ValidationIssue] = []
    requested_from: Optional[str] = Field(
        default=None,
        description="Who the missing info should be requested from (client/lawyer/manager)",
    )
    recommended_message: Optional[str] = Field(
        default=None,
        description="Draft message to send to the responsible party",
    )
    stage: str = Field(description="The stage being validated")


class ApplicationStatusUpdate(BaseModel):
    """Payload for transitioning an application to a new status."""

    new_status: ApplicationStatus
    reason: Optional[str] = None


class ApplicationListItem(BaseModel):
    """Lightweight application item for list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    status: ApplicationStatus
    mark_type: Optional[MarkType] = None
    mark_name: Optional[str] = None
    assigned_lawyer_id: Optional[int] = None
    assigned_manager_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
