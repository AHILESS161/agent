"""API v1 router — aggregates all endpoint sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.applications import router as applications_router
from app.api.v1.endpoints.assistant import router as assistant_router
from app.api.v1.endpoints.audit import router as audit_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.clients import router as clients_router
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.drafts import router as drafts_router
from app.api.v1.endpoints.extraction import router as extraction_router
from app.api.v1.endpoints.fees import router as fees_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.inbound import router as inbound_router
from app.api.v1.endpoints.intake import router as intake_router
from app.api.v1.endpoints.mvp import router as mvp_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.registry import router as registry_router
from app.api.v1.endpoints.risk import router as risk_router
from app.api.v1.endpoints.users import router as users_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health_router)
api_router.include_router(intake_router)
api_router.include_router(inbound_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(clients_router)
api_router.include_router(applications_router)
api_router.include_router(assistant_router)
api_router.include_router(documents_router)
api_router.include_router(extraction_router)
api_router.include_router(fees_router)
api_router.include_router(risk_router)
api_router.include_router(drafts_router)
api_router.include_router(mvp_router)
api_router.include_router(notifications_router)
api_router.include_router(registry_router)
api_router.include_router(audit_router)
api_router.include_router(admin_router)
