from types import SimpleNamespace
from app.infrastructure.database.models import ExtractionMethod
from app.services.risk_analysis import visual_evidence_state


def test_attachment_or_ocr_does_not_claim_visual_review():
    context = SimpleNamespace(image_attached=True, description="Описание пользователя")
    state = visual_evidence_state(context, None)
    assert state["image_upload"] == "attached"
    assert state["ocr"] == "not_recorded"
    document = SimpleNamespace(id=1, extraction_method=ExtractionMethod.ocr, char_count=12)
    state = visual_evidence_state(context, document)
    assert state["ocr"] == "text_found"
    assert state["visual_review"] == "not_recorded"
