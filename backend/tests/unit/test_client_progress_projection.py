import pytest
from app.services.client_progress import project_progress


@pytest.mark.parametrize("job,status,state", [
    ("queued", "draft", "queued"), ("running", "draft", "analyzing"),
    ("failed", "legal_review_in_progress", "failed"),
    ("completed", "draft", "incomplete"), (None, "closed", "closed"),
    (None, "submitted", "submitted"), (None, "document_approved", "documents"),
])
def test_progress_uses_actual_job_and_terminal_states(job, status, state):
    assert project_progress(status, job_status=job)["client_progress_state"] == state


def test_old_completed_assessment_does_not_hide_new_failed_job():
    assert project_progress("draft", assessments=(False,), job_status="failed")["client_progress_state"] == "failed"


def test_inconclusive_assessment_is_never_result_ready():
    assert project_progress("draft", assessments=(True,))["client_progress_state"] == "incomplete"
