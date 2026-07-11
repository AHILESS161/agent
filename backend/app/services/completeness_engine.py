"""
Completeness Engine — validates that a trademark application draft has all
required fields before advancing to a given processing stage.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Callable, List, Optional

from app.infrastructure.database.models import (
    ClientType,
    MarkType,
    TrademarkApplicationDraft,
)


# ---------------------------------------------------------------------------
# Stage enumeration
# ---------------------------------------------------------------------------

class ApplicationStage(str, Enum):
    """Logical stage used for completeness validation."""

    intake = "intake"
    classification = "classification"
    legal_review = "legal_review"
    conflict_search = "conflict_search"
    memo_generation = "memo_generation"
    document_generation = "document_generation"
    submission = "submission"


# ---------------------------------------------------------------------------
# Rule dataclass
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class CompletenessRule:
    """A single completeness rule evaluated against an application."""

    field: str
    message: str
    severity: str  # "blocking" | "non_blocking"
    stage: ApplicationStage
    condition: Callable[["TrademarkApplicationDraft"], bool]  # True when issue IS present
    applies_when: Callable[["TrademarkApplicationDraft"], bool] = dataclasses.field(
        default_factory=lambda: (lambda _app: True)
    )
    requested_from: str = "client"  # "client" | "lawyer" | "manager"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ValidationIssue:
    """A single issue found during validation."""

    field: str
    message: str
    severity: str
    stage: str
    requested_from: str


@dataclasses.dataclass
class CompletenessResult:
    """Return value of CompletenessEngine.validate()."""

    is_complete: bool
    blocking_issues: List[ValidationIssue]
    non_blocking_issues: List[ValidationIssue]
    requested_from: Optional[str]
    recommended_message: Optional[str]
    stage: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_foreign_elements(app: TrademarkApplicationDraft) -> bool:
    """Heuristic: mark text contains non-Cyrillic characters."""
    text = (app.mark_text or "") + (app.mark_name or "")
    return any(ord(c) < 0x0400 or ord(c) > 0x04FF for c in text if c.isalpha())


def _has_representatives(app: TrademarkApplicationDraft) -> bool:  # type: ignore[override]
    """Check if the application's client has any representatives loaded."""
    try:
        return bool(app.client and app.client.representatives)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CompletenessEngine:
    """
    Evaluates completeness rules against a TrademarkApplicationDraft.

    Usage::

        result = CompletenessEngine().validate(application, stage=ApplicationStage.document_generation)
        if not result.is_complete:
            ...
    """

    # All rules are evaluated in order; earlier rules take precedence for
    # the "requested_from" aggregate.
    RULES: List[CompletenessRule] = [
        # ---- Basic intake rules ------------------------------------------------
        CompletenessRule(
            field="mark_type",
            message="Тип обозначения (mark_type) не указан.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: app.mark_type is None,
            requested_from="client",
        ),
        CompletenessRule(
            field="mark_name",
            message="Наименование обозначения не указано.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not app.mark_name,
            requested_from="client",
        ),
        CompletenessRule(
            field="business_description",
            message="Описание деятельности заявителя не заполнено.",
            severity="non_blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not app.business_description,
            requested_from="client",
        ),
        CompletenessRule(
            field="goods_services_raw",
            message="Перечень товаров/услуг не указан.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not app.goods_services_raw,
            requested_from="client",
        ),
        # ---- Company → INN + OGRN required -------------------------------------
        CompletenessRule(
            field="inn",
            message="ИНН обязателен для юридического лица.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not (app.client and app.client.inn),
            applies_when=lambda app: bool(
                app.client and app.client.type == ClientType.company
            ),
            requested_from="client",
        ),
        CompletenessRule(
            field="ogrn_or_ogrnip",
            message="ОГРН обязателен для юридического лица.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not (app.client and app.client.ogrn_or_ogrnip),
            applies_when=lambda app: bool(
                app.client and app.client.type == ClientType.company
            ),
            requested_from="client",
        ),
        # ---- Individual client → INN required ----------------------------------
        CompletenessRule(
            field="inn",
            message="ИНН обязателен для физического лица.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not (app.client and app.client.inn),
            applies_when=lambda app: bool(
                app.client and app.client.type == ClientType.individual
            ),
            requested_from="client",
        ),
        # ---- Sole proprietor → ОГРНИП required ---------------------------------
        CompletenessRule(
            field="ogrn_or_ogrnip",
            message="ОГРНИП обязателен для индивидуального предпринимателя.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not (app.client and app.client.ogrn_or_ogrnip),
            applies_when=lambda app: bool(
                app.client and app.client.type == ClientType.sole_proprietor
            ),
            requested_from="client",
        ),
        # ---- Figurative / combined mark → image required -----------------------
        CompletenessRule(
            field="mark_image_file_id",
            message="Изображение обозначения (mark_image_file_id) обязательно для изобразительного или комбинированного знака.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not app.mark_image_file_id,
            applies_when=lambda app: app.mark_type
            in (MarkType.figurative, MarkType.combined),
            requested_from="client",
        ),
        # ---- Foreign elements → transliteration + translation ------------------
        CompletenessRule(
            field="transliteration",
            message="Транслитерация обязательна, если обозначение содержит иностранные слова.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not app.transliteration,
            applies_when=_has_foreign_elements,
            requested_from="client",
        ),
        CompletenessRule(
            field="translation",
            message="Перевод обязателен, если обозначение содержит иностранные слова.",
            severity="non_blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not app.translation,
            applies_when=_has_foreign_elements,
            requested_from="client",
        ),
        # ---- Colors claimed → color description required -----------------------
        CompletenessRule(
            field="colors_claimed",
            message="Описание цветового сочетания обязательно, если заявлены цвета.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: not app.colors_claimed,
            applies_when=lambda app: app.mark_type == MarkType.color,
            requested_from="client",
        ),
        # ---- Representative present → POA + personal data consent --------------
        CompletenessRule(
            field="poa_reference",
            message="Ссылка на доверенность обязательна при наличии представителя.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: any(
                not r.poa_reference
                for r in (
                    (app.client.representatives if app.client else None) or []
                )
            ),
            applies_when=_has_representatives,
            requested_from="client",
        ),
        CompletenessRule(
            field="personal_data_consent_reference",
            message="Ссылка на согласие на обработку персональных данных обязательна для представителей.",
            severity="blocking",
            stage=ApplicationStage.intake,
            condition=lambda app: any(
                not r.personal_data_consent_reference
                for r in (
                    (app.client.representatives if app.client else None) or []
                )
            ),
            applies_when=_has_representatives,
            requested_from="client",
        ),
        # ---- Classification stage rules ----------------------------------------
        CompletenessRule(
            field="goods_services_raw",
            message="Перечень товаров/услуг должен быть заполнен перед классификацией.",
            severity="blocking",
            stage=ApplicationStage.classification,
            condition=lambda app: not app.goods_services_raw,
            requested_from="client",
        ),
        # ---- Legal review stage ------------------------------------------------
        CompletenessRule(
            field="description_of_mark",
            message="Описание обозначения должно быть заполнено перед правовой экспертизой.",
            severity="non_blocking",
            stage=ApplicationStage.legal_review,
            condition=lambda app: not app.description_of_mark,
            requested_from="lawyer",
        ),
        # ---- Document generation hard-stop (all required fields) ---------------
        CompletenessRule(
            field="mark_type",
            message="[Документы] Тип обозначения обязателен.",
            severity="blocking",
            stage=ApplicationStage.document_generation,
            condition=lambda app: app.mark_type is None,
            requested_from="lawyer",
        ),
        CompletenessRule(
            field="goods_services_raw",
            message="[Документы] Перечень товаров/услуг обязателен.",
            severity="blocking",
            stage=ApplicationStage.document_generation,
            condition=lambda app: not app.goods_services_raw,
            requested_from="lawyer",
        ),
        CompletenessRule(
            field="territory",
            message="[Документы] Территория регистрации обязательна.",
            severity="blocking",
            stage=ApplicationStage.document_generation,
            condition=lambda app: not app.territory,
            requested_from="lawyer",
        ),
        CompletenessRule(
            field="description_of_mark",
            message="[Документы] Описание обозначения обязательно.",
            severity="blocking",
            stage=ApplicationStage.document_generation,
            condition=lambda app: not app.description_of_mark,
            requested_from="lawyer",
        ),
        CompletenessRule(
            field="inn",
            message="[Документы] ИНН обязателен для юридического лица.",
            severity="blocking",
            stage=ApplicationStage.document_generation,
            condition=lambda app: not (app.client and app.client.inn),
            applies_when=lambda app: bool(
                app.client and app.client.type == ClientType.company
            ),
            requested_from="lawyer",
        ),
        # ---- Submission hard-stop ----------------------------------------------
        CompletenessRule(
            field="mark_type",
            message="[Подача] Тип обозначения обязателен.",
            severity="blocking",
            stage=ApplicationStage.submission,
            condition=lambda app: app.mark_type is None,
            requested_from="manager",
        ),
        CompletenessRule(
            field="goods_services_raw",
            message="[Подача] Перечень товаров/услуг обязателен.",
            severity="blocking",
            stage=ApplicationStage.submission,
            condition=lambda app: not app.goods_services_raw,
            requested_from="manager",
        ),
        CompletenessRule(
            field="territory",
            message="[Подача] Территория регистрации обязательна.",
            severity="blocking",
            stage=ApplicationStage.submission,
            condition=lambda app: not app.territory,
            requested_from="manager",
        ),
    ]

    def validate(
        self,
        application: TrademarkApplicationDraft,
        stage: ApplicationStage,
    ) -> CompletenessResult:
        """
        Evaluate all rules applicable to *stage* against *application*.

        Returns a :class:`CompletenessResult`.
        """
        blocking: List[ValidationIssue] = []
        non_blocking: List[ValidationIssue] = []
        requestees: List[str] = []

        for rule in self.RULES:
            # Only evaluate rules at or before the requested stage.
            if not self._stage_reached(rule.stage, stage):
                continue

            # Check applies_when guard
            try:
                if not rule.applies_when(application):
                    continue
            except Exception:
                continue

            # Evaluate condition
            try:
                has_issue = rule.condition(application)
            except Exception:
                continue

            if not has_issue:
                continue

            issue = ValidationIssue(
                field=rule.field,
                message=rule.message,
                severity=rule.severity,
                stage=rule.stage.value,
                requested_from=rule.requested_from,
            )

            if rule.severity == "blocking":
                blocking.append(issue)
                requestees.append(rule.requested_from)
            else:
                non_blocking.append(issue)

        is_complete = len(blocking) == 0

        # Determine the primary requestee (most frequent among blocking issues)
        requested_from: Optional[str] = None
        if requestees:
            requested_from = max(set(requestees), key=requestees.count)

        recommended_message = self._build_recommended_message(
            blocking, non_blocking, requested_from, stage
        )

        return CompletenessResult(
            is_complete=is_complete,
            blocking_issues=blocking,
            non_blocking_issues=non_blocking,
            requested_from=requested_from,
            recommended_message=recommended_message,
            stage=stage.value,
        )

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    _STAGE_ORDER = [
        ApplicationStage.intake,
        ApplicationStage.classification,
        ApplicationStage.legal_review,
        ApplicationStage.conflict_search,
        ApplicationStage.memo_generation,
        ApplicationStage.document_generation,
        ApplicationStage.submission,
    ]

    def _stage_reached(self, rule_stage: ApplicationStage, current: ApplicationStage) -> bool:
        """Return True if rule_stage is at or before current in the pipeline."""
        try:
            return self._STAGE_ORDER.index(rule_stage) <= self._STAGE_ORDER.index(current)
        except ValueError:
            return False

    @staticmethod
    def _build_recommended_message(
        blocking: List[ValidationIssue],
        non_blocking: List[ValidationIssue],
        requested_from: Optional[str],
        stage: ApplicationStage,
    ) -> Optional[str]:
        """Build a human-readable message recommending what to request."""
        if not blocking and not non_blocking:
            return None

        parts: List[str] = []

        if blocking:
            fields = ", ".join(sorted({i.field for i in blocking}))
            parts.append(
                f"Необходимо предоставить следующие обязательные сведения: {fields}."
            )

        if non_blocking:
            fields = ", ".join(sorted({i.field for i in non_blocking}))
            parts.append(
                f"Рекомендуется также предоставить: {fields}."
            )

        recipient_map = {
            "client": "клиенту",
            "lawyer": "ответственному юристу",
            "manager": "менеджеру",
        }
        recipient = recipient_map.get(requested_from or "", "ответственному лицу")
        header = f"Запрос ({stage.value}): направить {recipient}. "
        return header + " ".join(parts)
