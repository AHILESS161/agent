"""Резервные ответы клиентского помощника без внешней модели."""

from app.api.v1.endpoints.assistant import _local_fallback_answer


def test_registration_risk_question_gets_useful_answer():
    answer = _local_fallback_answer(
        "Что может помешать регистрации?", has_application=False
    )

    assert "сходный знак" in answer
    assert "классах МКТУ" in answer
    assert "ошибка" not in answer.casefold()


def test_unrelated_question_stays_out_of_scope_without_case():
    answer = _local_fallback_answer("Напиши рецепт супа", has_application=False)

    assert answer == (
        "Я могу помочь только с регистрацией товарного знака "
        "и вашей заявкой в Регистре."
    )


def test_case_followup_gets_process_guidance():
    answer = _local_fallback_answer("Что делать дальше?", has_application=True)

    assert "четырёх основных шагов" in answer
