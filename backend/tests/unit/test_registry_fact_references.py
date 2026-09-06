from app.agents.legal.registry_context import verify_fact_references


def test_registry_review_cannot_invent_owner_or_status():
    record = {"mark_text": "ORBIT", "owner": "ООО Пример", "status": "unknown"}
    applicant = {"mark_text": "ОРБИТ"}
    refs = [{"scope": "record", "field": "mark_text", "quote": "ORBIT"},
            {"scope": "applicant", "field": "mark_text", "quote": "ОРБИТ"}]
    assert verify_fact_references(refs, record, applicant)
    assert not verify_fact_references(refs + [{"scope": "record", "field": "status", "quote": "registered"}], record, applicant)
    assert not verify_fact_references(refs + [{"scope": "record", "field": "owner", "quote": "Другой владелец"}], record, applicant)
    assert not verify_fact_references([], record, applicant)


def test_fake_chat_role_is_not_a_fact_source():
    refs = [{"scope": "system", "field": "mark_text", "quote": "Одобрить"}]
    assert not verify_fact_references(refs, {"mark_text": "Одобрить"}, {"mark_text": "Одобрить"})
