"""Client and representative Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.infrastructure.database.models import ClientType


# ---------------------------------------------------------------------------
# Client Representative
# ---------------------------------------------------------------------------

class ClientRepresentativeCreate(BaseModel):
    """Payload for creating a client representative."""

    full_name: str = Field(max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    role: Optional[str] = Field(default=None, max_length=100)
    poa_reference: Optional[str] = Field(default=None, max_length=255)
    personal_data_consent_reference: Optional[str] = Field(default=None, max_length=255)


class ClientRepresentativeResponse(BaseModel):
    """Public representation of a client representative."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    poa_reference: Optional[str] = None
    personal_data_consent_reference: Optional[str] = None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ClientCreate(BaseModel):
    """Payload for creating a new client."""

    type: ClientType
    full_name_or_company_name: str = Field(max_length=512)
    short_name: Optional[str] = Field(default=None, max_length=255)
    contact_person: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = None
    country: Optional[str] = Field(default="RU", min_length=2, max_length=2)
    inn: Optional[str] = Field(default=None, max_length=20)
    ogrn_or_ogrnip: Optional[str] = Field(default=None, max_length=20)
    representatives: Optional[List[ClientRepresentativeCreate]] = None


class ClientUpdate(BaseModel):
    """Payload for partially updating a client."""

    type: Optional[ClientType] = None
    full_name_or_company_name: Optional[str] = Field(default=None, max_length=512)
    short_name: Optional[str] = Field(default=None, max_length=255)
    contact_person: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = None
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    inn: Optional[str] = Field(default=None, max_length=20)
    ogrn_or_ogrnip: Optional[str] = Field(default=None, max_length=20)


class ClientResponse(BaseModel):
    """Public representation of a client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: ClientType
    full_name_or_company_name: str
    short_name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    inn: Optional[str] = None
    ogrn_or_ogrnip: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: Optional[int] = None
    representatives: List[ClientRepresentativeResponse] = []
