"""Schemas for application PDF/DOCX parsing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ParsedClientFields(BaseModel):
    """Client fields extracted from a filled application form."""

    full_name_or_company_name: Optional[str] = None
    short_name: Optional[str] = None
    inn: Optional[str] = None
    ogrn_or_ogrnip: Optional[str] = None
    kpp: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class ParsedApplicationFields(BaseModel):
    """Application fields extracted from a filled application form."""

    mark_name: Optional[str] = None
    mark_text: Optional[str] = None
    mark_type: Optional[str] = None
    mark_type_raw: Optional[str] = None
    description_of_mark: Optional[str] = None
    colors_claimed: Optional[str] = None
    transliteration: Optional[str] = None
    translation: Optional[str] = None
    mark_image_file_id: Optional[str] = None
    goods_services_raw: Optional[str] = None
    goods_services_description: Optional[str] = None
    mktu_classes: Optional[List[int]] = None
    correspondence_address: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_fax: Optional[str] = None
    contact_email: Optional[str] = None
    filing_date: Optional[str] = None
    filing_date_reception: Optional[str] = None
    is_volume: Optional[bool] = None
    is_holographic: Optional[bool] = None
    is_sound: Optional[bool] = None
    is_smell: Optional[bool] = None
    is_color_only: Optional[bool] = None
    is_collective: Optional[bool] = None


class ParsedRepresentativeFields(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    poa_reference: Optional[str] = None
    personal_data_consent_reference: Optional[str] = None
    patent_attorney_reg_number: Optional[str] = None


class ParsedPriorityFields(BaseModel):
    first_application_number: Optional[str] = None
    first_application_country: Optional[str] = None
    first_application_filing_date: Optional[str] = None
    original_application_number: Optional[str] = None
    international_registration_number: Optional[str] = None


class ParsedApplicationResponse(BaseModel):
    """Full response from PDF/DOCX parsing of an application form."""

    client: ParsedClientFields = Field(default_factory=ParsedClientFields)
    application: ParsedApplicationFields = Field(default_factory=ParsedApplicationFields)
    representative: ParsedRepresentativeFields = Field(
        default_factory=ParsedRepresentativeFields
    )
    priority: ParsedPriorityFields = Field(default_factory=ParsedPriorityFields)
    confidence: Dict[str, float] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    source_filename: Optional[str] = None
    source_text_length: int = 0
    extraction_method: str = "heuristic+llm_fallback"


class ParseApplicationFromTextRequest(BaseModel):
    """Plain-text variant of the parse endpoint (useful for testing)."""

    raw_text: str = Field(..., min_length=1)
    use_llm: bool = True