from typing import Protocol
from pydantic import BaseModel


class SearchQuery(BaseModel):
    mark_text: str
    mark_type: str | None = None
    classes: list[int] | None = None
    search_type: str = "exact"  # exact/fuzzy/phonetic/transliteration/semantic
    max_results: int = 50


class RegistryRecord(BaseModel):
    record_id: str
    external_id: str | None = None
    source: str | None = None  # registration / application
    mark_text: str
    mark_type: str
    owner: str
    classes: list[int]
    status: str  # registered/pending/expired/cancelled
    filing_date: str | None
    registration_date: str | None
    application_number: str | None = None
    registration_number: str | None = None
    image_url: str | None = None


class SubmissionPayload(BaseModel):
    applicant_data: dict
    mark_data: dict
    goods_services: list[dict]
    classes: list[int]
    description: str
    documents: list[str]


class SubmissionResult(BaseModel):
    success: bool
    external_id: str | None
    error_message: str | None


class ExternalStatusResult(BaseModel):
    external_id: str
    status: str
    updated_at: str
    details: dict | None = None


class TrademarkRegistryProvider(Protocol):
    async def search_marks(self, query: SearchQuery) -> list[RegistryRecord]: ...
    async def search_applications(self, query: SearchQuery) -> list[RegistryRecord]: ...
    async def get_record(self, record_id: str) -> RegistryRecord | None: ...
    async def submit_application(self, payload: SubmissionPayload) -> SubmissionResult: ...
    async def get_status(self, external_submission_id: str) -> ExternalStatusResult: ...
