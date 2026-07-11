"""Document generation and template Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.database.models import GenerationStatus, TemplateType


class DocumentTemplateResponse(BaseModel):
    """Public document template representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    template_type: TemplateType
    file_path: str
    version: str
    is_active: bool
    field_mapping_json: Optional[Any] = None
    created_at: datetime


class DocumentGenerateRequest(BaseModel):
    """Payload for requesting document package generation."""

    application_id: int
    template_id: int
    additional_context: Optional[dict[str, Any]] = Field(
        default=None,
        description="Extra context variables to merge into the template",
    )
    force_regenerate: bool = Field(
        default=False,
        description="Regenerate even if an approved package already exists",
    )


class DocumentPackageResponse(BaseModel):
    """Document package status and metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    template_id: int
    generation_status: GenerationStatus
    completeness_check_result_json: Optional[Any] = None
    file_path: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime


class DocumentApprovalRequest(BaseModel):
    """Payload for approving a generated document package."""

    package_id: int
    notes: Optional[str] = None


class DocumentPackageListResponse(BaseModel):
    """List of document packages for an application."""

    application_id: int
    packages: List[DocumentPackageResponse]
