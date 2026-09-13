"""Contracts for choosing between two proposed word marks, without a registry search."""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


class CompareMarksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    first: str = Field(min_length=1, max_length=120)
    second: str = Field(min_length=1, max_length=120)
    goods: str = Field(min_length=1, max_length=3000)

    @field_validator("first", "second", "goods", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return unicodedata.normalize("NFC", value).strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def different_designations(self):
        if " ".join(self.first.casefold().split()) == " ".join(self.second.casefold().split()):
            raise ValueError("Укажите два разных обозначения для сравнения")
        return self


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=700)]
Explanation = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1800)]
Recommendation = Literal["first", "second", "none", "inconclusive"]


class CandidateAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    category: Literal["fanciful", "arbitrary", "suggestive", "descriptive", "generic", "unclear"]
    distinctiveness: Literal["strong", "moderate", "weak", "unclear"]
    description_risk: Literal["low", "medium", "high", "unclear"]
    goods_relation: Explanation
    reasoning: Explanation
    strengths: list[ShortText] = Field(max_length=4)
    risks: list[ShortText] = Field(max_length=4)


class ComparisonAssessment(BaseModel):
    """Only analytical fields may come from the model; source and scope are server-owned."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    recommended: Recommendation
    summary: Explanation
    first: CandidateAssessment
    second: CandidateAssessment
    next_steps: list[ShortText] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def meaningful_recommendation(self):
        if self.recommended in {"first", "second"}:
            selected = getattr(self, self.recommended)
            if selected.distinctiveness in {"weak", "unclear"} or selected.description_risk in {"high", "unclear"}:
                raise ValueError("An unsupported candidate cannot be recommended")
        return self


class ComparedCandidate(CandidateAssessment):
    designation: str


class ComparisonSource(BaseModel):
    title: str
    url: str


class CompareMarksResponse(BaseModel):
    mode: Literal["analysis", "demo"]
    recommended: Recommendation
    summary: str
    first: ComparedCandidate
    second: ComparedCandidate
    next_steps: list[str]
    limitations: list[str]
    registry_checked: Literal[False] = False
    sources: list[ComparisonSource]
