"""
ApplicationStateMachine — manages state transitions for trademark application drafts.

All transitions are validated against a strict transition map. Every transition
creates an AuditLog entry and persists it via the provided AsyncSession.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTransitionError
from app.infrastructure.database.models import (
    ApplicationStatus,
    AuditLog,
    TrademarkApplicationDraft,
    User,
)


# ---------------------------------------------------------------------------
# Transition map
# ---------------------------------------------------------------------------

# Maps each state to the set of states it can transition INTO.
TRANSITION_MAP: Dict[ApplicationStatus, Set[ApplicationStatus]] = {
    ApplicationStatus.draft: {
        ApplicationStatus.info_requested,
        ApplicationStatus.classification_pending,
        ApplicationStatus.closed,
    },
    ApplicationStatus.info_requested: {
        ApplicationStatus.info_received,
        ApplicationStatus.closed,
    },
    ApplicationStatus.info_received: {
        ApplicationStatus.draft,
        ApplicationStatus.classification_pending,
        ApplicationStatus.closed,
    },
    ApplicationStatus.classification_pending: {
        ApplicationStatus.classification_review,
        ApplicationStatus.info_requested,
        ApplicationStatus.closed,
    },
    ApplicationStatus.classification_review: {
        ApplicationStatus.classification_approved,
        ApplicationStatus.classification_pending,
        ApplicationStatus.info_requested,
        ApplicationStatus.closed,
    },
    ApplicationStatus.classification_approved: {
        ApplicationStatus.legal_review_pending,
        ApplicationStatus.classification_review,
        ApplicationStatus.closed,
    },
    ApplicationStatus.legal_review_pending: {
        ApplicationStatus.legal_review_in_progress,
        ApplicationStatus.info_requested,
        ApplicationStatus.closed,
    },
    ApplicationStatus.legal_review_in_progress: {
        ApplicationStatus.legal_review_done,
        ApplicationStatus.legal_review_pending,
        ApplicationStatus.info_requested,
        ApplicationStatus.closed,
    },
    ApplicationStatus.legal_review_done: {
        ApplicationStatus.conflict_search_pending,
        ApplicationStatus.legal_review_in_progress,
        ApplicationStatus.info_requested,
        ApplicationStatus.closed,
    },
    ApplicationStatus.conflict_search_pending: {
        ApplicationStatus.conflict_search_in_progress,
        ApplicationStatus.info_requested,
        ApplicationStatus.closed,
    },
    ApplicationStatus.conflict_search_in_progress: {
        ApplicationStatus.conflict_search_done,
        ApplicationStatus.conflict_search_pending,
        ApplicationStatus.closed,
    },
    ApplicationStatus.conflict_search_done: {
        ApplicationStatus.memo_generation,
        ApplicationStatus.conflict_search_in_progress,
        ApplicationStatus.info_requested,
        ApplicationStatus.closed,
    },
    ApplicationStatus.memo_generation: {
        ApplicationStatus.memo_approved,
        ApplicationStatus.conflict_search_done,
        ApplicationStatus.info_requested,
        ApplicationStatus.closed,
    },
    ApplicationStatus.memo_approved: {
        ApplicationStatus.document_generation,
        ApplicationStatus.memo_generation,
        ApplicationStatus.closed,
    },
    ApplicationStatus.document_generation: {
        ApplicationStatus.document_approved,
        ApplicationStatus.info_requested,
        ApplicationStatus.closed,
    },
    ApplicationStatus.document_approved: {
        ApplicationStatus.submitted,
        ApplicationStatus.document_generation,
        ApplicationStatus.closed,
    },
    ApplicationStatus.submitted: {
        ApplicationStatus.closed,
    },
    ApplicationStatus.closed: set(),  # Terminal state — no outgoing transitions
}


# ---------------------------------------------------------------------------
# State machine class
# ---------------------------------------------------------------------------

class ApplicationStateMachine:
    """
    Validates and executes transitions for :class:`TrademarkApplicationDraft`.

    Example::

        sm = ApplicationStateMachine(session)
        await sm.transition(
            application,
            new_status=ApplicationStatus.classification_pending,
            user=current_user,
            reason="Intake data received",
        )
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def transition(
        self,
        application: TrademarkApplicationDraft,
        new_status: ApplicationStatus,
        user: Optional[User] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TrademarkApplicationDraft:
        """
        Attempt to transition *application* to *new_status*.

        Raises
        ------
        InvalidTransitionError
            If the transition is not allowed by :data:`TRANSITION_MAP`.

        Returns the updated application (still within the session — caller must commit).
        """
        current_status = application.status

        self._validate_transition(current_status, new_status)

        old_value = {"status": current_status.value}
        new_value = {"status": new_status.value}
        if reason:
            new_value["reason"] = reason

        # Apply the transition
        application.status = new_status
        application.updated_at = datetime.now(timezone.utc)

        # Create audit log entry
        audit_entry = AuditLog(
            user_id=user.id if user else None,
            application_id=application.id,
            action="status_transition",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(application.id),
            old_value_json=old_value,
            new_value_json=new_value,
            ip_address=ip_address,
        )
        self._session.add(audit_entry)

        return application

    # ---------------------------------------------------------------------------
    # Query helpers
    # ---------------------------------------------------------------------------

    def allowed_transitions(
        self, current_status: ApplicationStatus
    ) -> Set[ApplicationStatus]:
        """Return the set of states reachable from *current_status*."""
        return TRANSITION_MAP.get(current_status, set())

    def can_transition(
        self,
        current_status: ApplicationStatus,
        new_status: ApplicationStatus,
    ) -> bool:
        """Return True if the transition current → new is allowed."""
        return new_status in TRANSITION_MAP.get(current_status, set())

    # ---------------------------------------------------------------------------
    # Private
    # ---------------------------------------------------------------------------

    def _validate_transition(
        self,
        from_status: ApplicationStatus,
        to_status: ApplicationStatus,
    ) -> None:
        allowed = TRANSITION_MAP.get(from_status, set())
        if to_status not in allowed:
            raise InvalidTransitionError(
                from_state=from_status.value,
                to_state=to_status.value,
            )
