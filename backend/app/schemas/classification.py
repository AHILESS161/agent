"""Nice classification Pydantic schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.database.models import ItemSource, NiceCategory


class ClassSuggestionRequest(BaseModel):
    """Request for Nice class suggestions for an application."""

    application_id: int
    goods_services_text: Optional[str] = Field(
        default=None,
        description="If provided, override the application's goods_services_raw",
    )
    force_refresh: bool = False


class GoodsServicesItemCreate(BaseModel):
    """Payload for manually adding a goods/services item."""

    raw_text: str
    normalized_text: Optional[str] = None
    proposed_class: int = Field(ge=1, le=45)
    source: ItemSource = ItemSource.manual


class GoodsServicesItemResponse(BaseModel):
    """Goods/services item representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    raw_text: str
    normalized_text: Optional[str] = None
    proposed_class: int
    approved_class: Optional[int] = None
    source: ItemSource


class NiceClassSuggestionResponse(BaseModel):
    """Single Nice class suggestion from the AI agent."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    class_number: int
    class_description: Optional[str] = None
    rationale: Optional[str] = None
    confidence: Optional[float] = None
    category: Optional[NiceCategory] = None
    risks_if_omitted: Optional[str] = None
    risks_if_included: Optional[str] = None
    approved: Optional[bool] = None
    approved_by: Optional[int] = None


class ClassSuggestionResponse(BaseModel):
    """Aggregated classification suggestion response."""

    application_id: int
    suggestions: List[NiceClassSuggestionResponse]
    goods_services_items: List[GoodsServicesItemResponse] = []
    summary: Optional[str] = None
    confidence: Optional[float] = None


class ManualClassRequest(BaseModel):
    """Класс, добавленный специалистом вручную.

    Подбор по описанию деятельности покрывает не всё: специалист
    вправе добавить класс, которого система не предложила.
    """

    class_number: int = Field(ge=1, le=45)
    class_description: Optional[str] = Field(default=None, max_length=2000)
    rationale: Optional[str] = Field(default=None, max_length=2000)


class ClassApprovalRequest(BaseModel):
    """Payload for a lawyer to approve or reject a class suggestion."""

    suggestion_id: int
    approved: bool
    class_description: Optional[str] = Field(
        default=None,
        max_length=4000,
        description="Точный перечень товаров и услуг, который заявитель подтверждает",
    )
    override_class: Optional[int] = Field(
        default=None, ge=1, le=45, description="Override the AI-suggested class number"
    )
