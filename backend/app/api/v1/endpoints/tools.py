"""Authenticated tools that return a result without creating or changing a case."""

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.dependencies import get_llm_provider
from app.api.middleware.rate_limit import Rule, _limiter
from app.core.config import settings
from app.core.security import get_current_user
from app.infrastructure.database.models import User
from app.infrastructure.llm.base import BaseLLMProvider
from app.schemas.mark_comparison import CompareMarksRequest, CompareMarksResponse
from app.services.mark_comparison import compare_marks

router = APIRouter(prefix="/tools", tags=["client-tools"])


@router.post("/compare-marks", response_model=CompareMarksResponse)
async def compare_proposed_marks(
    payload: CompareMarksRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    provider: BaseLLMProvider = Depends(get_llm_provider),
) -> CompareMarksResponse:
    response.headers["Cache-Control"] = "no-store"
    if settings.RATE_LIMIT_ENABLED:
        allowed, retry = _limiter.check(f"user:{current_user.id}:compare-marks", Rule(6, 60))
        if not allowed:
            raise HTTPException(429, "Слишком много сравнений. Повторите позже.", headers={"Retry-After": str(retry)})
    return await compare_marks(payload, provider)
