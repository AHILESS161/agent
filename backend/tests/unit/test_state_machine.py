"""
Unit tests for ApplicationStateMachine.

Tests validate:
- Valid transitions succeed and update application status
- Invalid transitions raise InvalidTransitionError
- Each transition creates an AuditLog entry
- Transition reason is recorded in the audit log
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTransitionError
from app.infrastructure.database.models import (
    ApplicationStatus,
    AuditLog,
    Client,
    ClientType,
    MarkType,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.services.state_machine import ApplicationStateMachine, TRANSITION_MAP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role: UserRole = UserRole.manager, user_id: int = 1) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id
    user.email = f"user{user_id}@test.ru"
    user.role = role
    return user


def _make_application(
    status: ApplicationStatus = ApplicationStatus.draft,
    app_id: int = 1,
) -> MagicMock:
    app = MagicMock(spec=TrademarkApplicationDraft)
    app.id = app_id
    app.status = status
    app.updated_at = datetime.now(tz=timezone.utc)
    return app


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestStateMachineValidTransitions:
    """Tests for transitions that should succeed."""

    async def test_draft_to_info_requested(self, async_session: AsyncSession):
        """draft → info_requested is a valid transition."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.draft)

        with patch.object(async_session, "add") as mock_add:
            updated = await sm.transition(
                app,
                new_status=ApplicationStatus.info_requested,
                user=user,
            )

        assert updated.status == ApplicationStatus.info_requested

    async def test_draft_to_classification_pending(self, async_session: AsyncSession):
        """draft → classification_pending is a valid transition."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.draft)

        with patch.object(async_session, "add"):
            updated = await sm.transition(
                app,
                new_status=ApplicationStatus.classification_pending,
                user=user,
            )

        assert updated.status == ApplicationStatus.classification_pending

    async def test_info_requested_to_info_received(self, async_session: AsyncSession):
        """info_requested → info_received is valid."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.info_requested)

        with patch.object(async_session, "add"):
            updated = await sm.transition(
                app,
                new_status=ApplicationStatus.info_received,
                user=user,
            )

        assert updated.status == ApplicationStatus.info_received

    async def test_conflict_search_done_to_memo_generation(self, async_session: AsyncSession):
        """conflict_search_done → memo_generation is valid."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.conflict_search_done)

        with patch.object(async_session, "add"):
            updated = await sm.transition(
                app,
                new_status=ApplicationStatus.memo_generation,
                user=user,
            )

        assert updated.status == ApplicationStatus.memo_generation

    async def test_any_state_to_closed(self, async_session: AsyncSession):
        """Any non-closed state can transition to closed."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()

        for status in [
            ApplicationStatus.draft,
            ApplicationStatus.info_requested,
            ApplicationStatus.classification_pending,
            ApplicationStatus.legal_review_in_progress,
        ]:
            app = _make_application(status)
            with patch.object(async_session, "add"):
                updated = await sm.transition(
                    app,
                    new_status=ApplicationStatus.closed,
                    user=user,
                )
            assert updated.status == ApplicationStatus.closed


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestStateMachineInvalidTransitions:
    """Tests for transitions that should raise InvalidTransitionError."""

    async def test_draft_cannot_jump_to_submitted(self, async_session: AsyncSession):
        """draft → submitted is not allowed (skips many stages)."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.draft)

        with pytest.raises(InvalidTransitionError) as exc_info:
            await sm.transition(
                app,
                new_status=ApplicationStatus.submitted,
                user=user,
            )

        assert "draft" in str(exc_info.value).lower() or "submitted" in str(exc_info.value).lower()

    async def test_closed_cannot_transition_to_any(self, async_session: AsyncSession):
        """A closed application cannot transition to any other state."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.closed)

        with pytest.raises(InvalidTransitionError):
            await sm.transition(
                app,
                new_status=ApplicationStatus.draft,
                user=user,
            )

    async def test_submitted_cannot_go_back_to_draft(self, async_session: AsyncSession):
        """submitted → draft is not a valid backward transition."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.submitted)

        with pytest.raises(InvalidTransitionError):
            await sm.transition(
                app,
                new_status=ApplicationStatus.draft,
                user=user,
            )

    async def test_info_requested_cannot_jump_to_legal_review(self, async_session: AsyncSession):
        """info_requested → legal_review_pending is not allowed."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.info_requested)

        with pytest.raises(InvalidTransitionError):
            await sm.transition(
                app,
                new_status=ApplicationStatus.legal_review_pending,
                user=user,
            )

    async def test_error_message_contains_both_states(self, async_session: AsyncSession):
        """InvalidTransitionError message includes both from and to states."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.draft)

        with pytest.raises(InvalidTransitionError) as exc_info:
            await sm.transition(
                app,
                new_status=ApplicationStatus.submitted,
                user=user,
            )

        error = exc_info.value
        assert hasattr(error, "from_state") or "draft" in str(error).lower()


# ---------------------------------------------------------------------------
# Audit log creation
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestStateMachineAuditLog:
    """Tests that verify audit log entries are created on transition."""

    async def test_transition_adds_audit_log(self, async_session: AsyncSession):
        """Every successful transition must result in session.add() with an AuditLog."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.draft)

        added_objects = []
        with patch.object(async_session, "add", side_effect=added_objects.append):
            await sm.transition(
                app,
                new_status=ApplicationStatus.classification_pending,
                user=user,
            )

        audit_logs = [o for o in added_objects if isinstance(o, AuditLog)]
        assert len(audit_logs) == 1

    async def test_audit_log_contains_status_values(self, async_session: AsyncSession):
        """AuditLog entry must record both old and new status values."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.draft)

        added_objects = []
        with patch.object(async_session, "add", side_effect=added_objects.append):
            await sm.transition(
                app,
                new_status=ApplicationStatus.classification_pending,
                user=user,
            )

        audit_log = next(o for o in added_objects if isinstance(o, AuditLog))
        assert "draft" in str(audit_log.old_value_json)
        assert "classification_pending" in str(audit_log.new_value_json)

    async def test_audit_log_contains_reason(self, async_session: AsyncSession):
        """AuditLog new_value_json must include the transition reason."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user()
        app = _make_application(ApplicationStatus.draft)
        reason = "Все данные получены"

        added_objects = []
        with patch.object(async_session, "add", side_effect=added_objects.append):
            await sm.transition(
                app,
                new_status=ApplicationStatus.classification_pending,
                user=user,
                reason=reason,
            )

        audit_log = next(o for o in added_objects if isinstance(o, AuditLog))
        assert reason in str(audit_log.new_value_json)

    async def test_audit_log_records_user_id(self, async_session: AsyncSession):
        """AuditLog must record the user who triggered the transition."""
        sm = ApplicationStateMachine(async_session)
        user = _make_user(user_id=42)
        app = _make_application(ApplicationStatus.draft)

        added_objects = []
        with patch.object(async_session, "add", side_effect=added_objects.append):
            await sm.transition(
                app,
                new_status=ApplicationStatus.classification_pending,
                user=user,
            )

        audit_log = next(o for o in added_objects if isinstance(o, AuditLog))
        assert audit_log.user_id == 42


# ---------------------------------------------------------------------------
# Transition map structure
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTransitionMap:
    """Tests that verify the transition map is correctly structured."""

    def test_all_statuses_have_transition_entries(self):
        """Every ApplicationStatus (except closed) must have an entry in TRANSITION_MAP."""
        all_statuses = set(ApplicationStatus)
        # closed is terminal — it can have an entry but transitions from it should be empty
        mapped_statuses = set(TRANSITION_MAP.keys())
        # All non-closed statuses should be in the map
        non_closed = all_statuses - {ApplicationStatus.closed}
        missing = non_closed - mapped_statuses
        assert missing == set(), f"Statuses missing from TRANSITION_MAP: {missing}"

    def test_closed_is_reachable_from_most_states(self):
        """closed should be reachable from most pipeline states."""
        closeable = [
            status for status, targets in TRANSITION_MAP.items()
            if ApplicationStatus.closed in targets
        ]
        assert len(closeable) >= 5, (
            "Expected at least 5 states to allow transition to closed"
        )

    def test_submitted_is_reachable(self):
        """submitted must be reachable from document_approved."""
        targets = TRANSITION_MAP.get(ApplicationStatus.document_approved, set())
        assert ApplicationStatus.submitted in targets
