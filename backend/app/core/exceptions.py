"""Custom exception classes and FastAPI exception handlers."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class AppError(Exception):
    """Base class for all application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


# ---------------------------------------------------------------------------
# Concrete exceptions
# ---------------------------------------------------------------------------

class ValidationError(AppError):
    """Raised when incoming data fails business-rule validation."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation_error"

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message, details)


class NotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"

    def __init__(self, resource: str, resource_id: Any = None) -> None:
        detail = f"{resource} not found"
        if resource_id is not None:
            detail = f"{resource} with id '{resource_id}' not found"
        super().__init__(detail, {"resource": resource, "id": resource_id})


class AuthorizationError(AppError):
    """Raised when a user lacks permission for an action."""

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "authorization_error"

    def __init__(self, message: str = "You do not have permission to perform this action") -> None:
        super().__init__(message)


class CompletenessError(AppError):
    """Raised when an application is missing required fields for a given stage."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "completeness_error"

    def __init__(
        self,
        message: str,
        blocking_issues: Optional[list[str]] = None,
        stage: Optional[str] = None,
    ) -> None:
        super().__init__(
            message,
            {
                "blocking_issues": blocking_issues or [],
                "stage": stage,
            },
        )
        self.blocking_issues = blocking_issues or []
        self.stage = stage


class ProviderError(AppError):
    """Raised when an external provider (LLM, search, FIPS) returns an error."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "provider_error"

    def __init__(self, provider: str, message: str, details: Optional[Any] = None) -> None:
        super().__init__(f"Provider '{provider}' error: {message}", details)
        self.provider = provider


class InvalidTransitionError(AppError):
    """Raised when an illegal state-machine transition is attempted."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "invalid_transition"

    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(
            f"Cannot transition from '{from_state}' to '{to_state}'",
            {"from": from_state, "to": to_state},
        )


class ConflictError(AppError):
    """Raised when a resource already exists (e.g. duplicate email)."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message, details)


# ---------------------------------------------------------------------------
# FastAPI exception handlers
# ---------------------------------------------------------------------------

def _error_response(exc: AppError, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "path": str(request.url.path),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI application."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        request: Request, exc: AuthorizationError
    ) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(CompletenessError)
    async def completeness_error_handler(
        request: Request, exc: CompletenessError
    ) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(ProviderError)
    async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(InvalidTransitionError)
    async def invalid_transition_handler(
        request: Request, exc: InvalidTransitionError
    ) -> JSONResponse:
        return _error_response(exc, request)

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return _error_response(exc, request)
