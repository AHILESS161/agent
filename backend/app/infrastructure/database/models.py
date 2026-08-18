"""SQLAlchemy 2.0 ORM models for the Trademark Registration System."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.session import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    admin = "admin"
    lawyer = "lawyer"
    manager = "manager"
    client = "client"


class ClientType(str, enum.Enum):
    company = "company"
    individual = "individual"
    sole_proprietor = "sole_proprietor"


class ApplicationStatus(str, enum.Enum):
    # 18 states
    draft = "draft"
    info_requested = "info_requested"
    info_received = "info_received"
    classification_pending = "classification_pending"
    classification_review = "classification_review"
    classification_approved = "classification_approved"
    legal_review_pending = "legal_review_pending"
    legal_review_in_progress = "legal_review_in_progress"
    legal_review_done = "legal_review_done"
    conflict_search_pending = "conflict_search_pending"
    conflict_search_in_progress = "conflict_search_in_progress"
    conflict_search_done = "conflict_search_done"
    memo_generation = "memo_generation"
    memo_approved = "memo_approved"
    document_generation = "document_generation"
    document_approved = "document_approved"
    submitted = "submitted"
    closed = "closed"


class MarkType(str, enum.Enum):
    word = "word"
    figurative = "figurative"
    combined = "combined"
    three_d = "3d"
    sound = "sound"
    color = "color"
    other = "other"


class ReviewType(str, enum.Enum):
    absolute = "absolute"
    relative = "relative"
    combined = "combined"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ReviewerDecision(str, enum.Enum):
    approve = "approve"
    reject = "reject"
    modify = "modify"


class ConflictDecision(str, enum.Enum):
    conflict = "conflict"
    no_conflict = "no_conflict"
    needs_review = "needs_review"


class FindingType(str, enum.Enum):
    absolute = "absolute"
    relative = "relative"


class FindingSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    blocking = "blocking"


class ItemSource(str, enum.Enum):
    ai = "ai"
    manual = "manual"
    imported = "imported"


class NiceCategory(str, enum.Enum):
    primary = "primary"
    secondary = "secondary"
    borderline = "borderline"


class SearchJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class GenerationStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    generated = "generated"
    failed = "failed"


class TemplateType(str, enum.Enum):
    application = "application"
    missing_info_letter = "missing_info_letter"
    legal_memo = "legal_memo"
    power_of_attorney = "power_of_attorney"


class CasePriority(str, enum.Enum):
    """Срочность дела в работе поверенного.

    Не имеет отношения к приоритету заявки по статье 1495 ГК РФ:
    то — дата, от которой считается старшинство, и живёт в поле
    ``priority_claim``.
    """

    low = "low"
    medium = "medium"
    high = "high"


class RecommendedAction(str, enum.Enum):
    proceed = "proceed"
    modify = "modify"
    withdraw = "withdraw"
    further_review = "further_review"


class NotificationType(str, enum.Enum):
    info = "info"
    warning = "warning"
    action_required = "action_required"
    status_change = "status_change"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    waiting_human_review = "waiting_human_review"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"
    cancelled = "cancelled"


class KnowledgeSourceType(str, enum.Enum):
    law = "law"
    regulation = "regulation"
    methodology = "methodology"
    template = "template"
    practice = "practice"


class AgentRunStatus(str, enum.Enum):
    started = "started"
    running = "running"
    completed = "completed"
    failed = "failed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Как обращаться к человеку. ФИО хранится как «Фамилия Имя
    # Отчество», и приветствие по первому слову выходит по фамилии —
    # так к людям не обращаются.
    preferred_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole"), nullable=False, default=UserRole.client
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="user", foreign_keys="AuditLog.user_id"
    )


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[ClientType] = mapped_column(
        Enum(ClientType, name="clienttype"), nullable=False
    )
    full_name_or_company_name: Mapped[str] = mapped_column(String(512), nullable=False)
    short_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    inn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ogrn_or_ogrnip: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_user_id])
    representatives: Mapped[list["ClientRepresentative"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    applications: Mapped[list["TrademarkApplicationDraft"]] = relationship(
        back_populates="client"
    )


class ClientRepresentative(Base):
    __tablename__ = "client_representatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    poa_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    personal_data_consent_reference: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # Relationships
    client: Mapped["Client"] = relationship(back_populates="representatives")


class TrademarkApplicationDraft(Base):
    __tablename__ = "trademark_application_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assigned_lawyer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_manager_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="applicationstatus"),
        nullable=False,
        default=ApplicationStatus.draft,
    )
    mark_type: Mapped[Optional[MarkType]] = mapped_column(
        Enum(MarkType, name="marktype"), nullable=True
    )
    mark_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mark_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mark_image_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    colors_claimed: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transliteration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_of_mark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    goods_services_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    territory: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    priority_claim: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Срочность в работе — не конвенционный приоритет заявки.
    priority: Mapped[CasePriority] = mapped_column(
        Enum(CasePriority, name="casepriority"),
        nullable=False,
        default=CasePriority.medium,
        server_default=CasePriority.medium.value,
    )
    # Кто завёл дело. Определяет, кому оно видно: поверенные
    # ведут свои дела и не должны мешать друг другу.
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    client: Mapped["Client"] = relationship(back_populates="applications")
    assigned_lawyer: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_lawyer_id]
    )
    assigned_manager: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_manager_id]
    )
    goods_services_items: Mapped[list["GoodsServicesItem"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    nice_class_suggestions: Mapped[list["NiceClassSuggestion"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    legal_reviews: Mapped[list["LegalReview"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    conflict_search_jobs: Mapped[list["ConflictSearchJob"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    conflict_search_results: Mapped[list["ConflictSearchResult"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    recommendation_memos: Mapped[list["RecommendationMemo"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    document_packages: Mapped[list["DocumentPackage"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="application"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="application", foreign_keys="AuditLog.application_id"
    )
    source_documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        foreign_keys="SourceDocument.application_id",
    )


class GoodsServicesItem(Base):
    __tablename__ = "goods_services_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proposed_class: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_class: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[ItemSource] = mapped_column(
        Enum(ItemSource, name="itemsource"), nullable=False, default=ItemSource.manual
    )

    # Relationships
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        back_populates="goods_services_items"
    )


class NiceClassSuggestion(Base):
    __tablename__ = "nice_class_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    class_number: Mapped[int] = mapped_column(Integer, nullable=False)
    class_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    category: Mapped[Optional[NiceCategory]] = mapped_column(
        Enum(NiceCategory, name="nicecategory"), nullable=True
    )
    risks_if_omitted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risks_if_included: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        back_populates="nice_class_suggestions"
    )
    approver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by])


class LegalReview(Base):
    __tablename__ = "legal_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_type: Mapped[ReviewType] = mapped_column(
        Enum(ReviewType, name="reviewtype"), nullable=False
    )
    absolute_grounds_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    relative_grounds_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_level: Mapped[Optional[RiskLevel]] = mapped_column(
        Enum(RiskLevel, name="risklevel"), nullable=True
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    citations_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    reviewer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewer_decision: Mapped[Optional[ReviewerDecision]] = mapped_column(
        Enum(ReviewerDecision, name="reviewerdecision"), nullable=True
    )
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        back_populates="legal_reviews"
    )
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewer_id])
    findings: Mapped[list["LegalFinding"]] = relationship(
        back_populates="legal_review", cascade="all, delete-orphan"
    )


class LegalFinding(Base):
    __tablename__ = "legal_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    legal_review_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("legal_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_type: Mapped[FindingType] = mapped_column(
        Enum(FindingType, name="findingtype"), nullable=False
    )
    ground_article: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(
        Enum(FindingSeverity, name="findingseverity"), nullable=False
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_reference: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    legal_review: Mapped["LegalReview"] = relationship(back_populates="findings")


class ConflictSearchJob(Base):
    __tablename__ = "conflict_search_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[SearchJobStatus] = mapped_column(
        Enum(SearchJobStatus, name="searchjobstatus"),
        nullable=False,
        default=SearchJobStatus.queued,
    )
    search_strategy_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        back_populates="conflict_search_jobs"
    )
    results: Mapped[list["ConflictSearchResult"]] = relationship(
        back_populates="search_job", cascade="all, delete-orphan"
    )


class ConflictSearchResult(Base):
    __tablename__ = "conflict_search_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    search_job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conflict_search_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    matched_mark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    classes: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    filing_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    phonetic_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    translit_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    semantic_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    visual_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conflict_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer_decision: Mapped[Optional[ConflictDecision]] = mapped_column(
        Enum(ConflictDecision, name="conflictdecision"), nullable=True
    )

    # Relationships
    search_job: Mapped["ConflictSearchJob"] = relationship(back_populates="results")
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        back_populates="conflict_search_results"
    )


class RecommendationMemo(Base):
    __tablename__ = "recommendation_memos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[Optional[RecommendedAction]] = mapped_column(
        Enum(RecommendedAction, name="recommendedaction"), nullable=True
    )
    recommended_classes_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    key_conflicts_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    key_risks_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        back_populates="recommendation_memos"
    )
    approver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by])


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    template_type: Mapped[TemplateType] = mapped_column(
        Enum(TemplateType, name="templatetype"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    field_mapping_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    packages: Mapped[list["DocumentPackage"]] = relationship(back_populates="template")


class DocumentPackage(Base):
    __tablename__ = "document_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_templates.id", ondelete="RESTRICT"), nullable=False
    )
    generation_status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus, name="generationstatus"),
        nullable=False,
        default=GenerationStatus.pending,
    )
    completeness_check_result_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        back_populates="document_packages"
    )
    template: Mapped["DocumentTemplate"] = relationship(back_populates="packages")
    approver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by])


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    external_submission_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        back_populates="submissions"
    )
    status_events: Mapped[list["SubmissionStatusEvent"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )


class SubmissionStatusEvent(Base):
    __tablename__ = "submission_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    new_status: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_payload_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    notification_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    submission: Mapped["Submission"] = relationship(back_populates="status_events")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notificationtype"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="notifications")
    application: Mapped[Optional["TrademarkApplicationDraft"]] = relationship(
        back_populates="notifications"
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    application_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    old_value_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    new_value_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        back_populates="audit_logs", foreign_keys=[user_id]
    )
    application: Mapped[Optional["TrademarkApplicationDraft"]] = relationship(
        back_populates="audit_logs", foreign_keys=[application_id]
    )


class PromptDefinition(Base):
    __tablename__ = "prompt_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    prompt_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    output_schema_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    examples_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    guardrails_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus, name="agentrunstatus"),
        nullable=False,
        default=AgentRunStatus.started,
    )
    input_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    output_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    application: Mapped[Optional["TrademarkApplicationDraft"]] = relationship(
        back_populates="agent_runs"
    )


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[KnowledgeSourceType] = mapped_column(
        Enum(KnowledgeSourceType, name="knowledgesourcetype"), nullable=False
    )
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    embedding_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    source: Mapped["KnowledgeSource"] = relationship(back_populates="chunks")


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="jobstatus"),
        nullable=False,
        default=JobStatus.queued,
    )
    payload_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    result_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ===========================================================================
# Документы, извлечённые поля и подтверждения специалистом
# ---------------------------------------------------------------------------
# Раньше загруженный файл нигде не сохранялся: intake-эндпоинт парсил байты
# и выбрасывал их. Эти сущности дают прослеживаемость от исходного файла
# до значения, попавшего в заявление: файл -> страница -> поле -> кандидаты
# -> решение специалиста.
# ===========================================================================

class DocumentKind(str, enum.Enum):
    """Тип загруженного документа."""

    trademark_application = "trademark_application"   # заявка на ТЗ (бланк Роспатента)
    egrul_extract = "egrul_extract"                   # выписка ЕГРЮЛ
    egrip_extract = "egrip_extract"                   # выписка ЕГРИП
    unknown_registry_extract = "unknown_registry_extract"  # реестровая справка, тип неясен
    power_of_attorney = "power_of_attorney"           # доверенность
    passport = "passport"                             # паспорт заявителя — чувствительные данные
    mark_image = "mark_image"                         # изображение обозначения
    mark_audio = "mark_audio"                         # аудиозапись звукового обозначения
    other = "other"
    unknown = "unknown"


class DocumentProcessingStatus(str, enum.Enum):
    uploaded = "uploaded"
    extracting = "extracting"
    extracted = "extracted"
    failed = "failed"
    rejected = "rejected"      # не прошёл проверку типа/размера/MIME


class ExtractionMethod(str, enum.Enum):
    """Как получено значение. Порядок соответствует убыванию доверия."""

    pdf_text_layer = "pdf_text_layer"
    docx_parser = "docx_parser"
    plain_text = "plain_text"
    regex = "regex"
    rule = "rule"
    ocr = "ocr"
    llm_fallback = "llm_fallback"
    manual = "manual"


class FieldStatus(str, enum.Enum):
    """Статус извлечённого поля в процессе проверки специалистом."""

    matched = "matched"             # извлечено и прошло валидацию
    missing = "missing"             # обязательное поле не найдено
    conflict = "conflict"           # несколько несовместимых кандидатов
    needs_review = "needs_review"   # требует глаз специалиста
    confirmed = "confirmed"         # подтверждено специалистом
    rejected = "rejected"           # специалист отклонил значение
    left_empty = "left_empty"       # специалист сознательно оставил пустым


class ConfirmationAction(str, enum.Enum):
    accept = "accept"
    edit = "edit"
    reject = "reject"
    leave_empty = "leave_empty"


class SourceChannel(str, enum.Enum):
    """Канал поступления документа (используется inbound router'ом)."""

    manual_upload = "manual_upload"
    crm = "crm"
    email = "email"
    webhook = "webhook"
    api = "api"


class SourceDocument(Base):
    """Оригинал загруженного файла и метаданные его обработки."""

    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    uploaded_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # --- файл ---
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    declared_content_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detected_mime: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    # SHA-256 не уникален: один и тот же файл может законно относиться
    # к нескольким делам. Индекс нужен для дедупликации в рамках дела.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # --- классификация ---
    document_kind: Mapped[DocumentKind] = mapped_column(
        Enum(DocumentKind, name="documentkind"),
        nullable=False,
        default=DocumentKind.unknown,
    )
    kind_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kind_requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # --- обработка ---
    processing_status: Mapped[DocumentProcessingStatus] = mapped_column(
        Enum(DocumentProcessingStatus, name="documentprocessingstatus"),
        nullable=False,
        default=DocumentProcessingStatus.uploaded,
    )
    extraction_method: Mapped[Optional[ExtractionMethod]] = mapped_column(
        Enum(ExtractionMethod, name="extractionmethod"), nullable=True
    )
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- происхождение ---
    source_channel: Mapped[SourceChannel] = mapped_column(
        Enum(SourceChannel, name="sourcechannel"),
        nullable=False,
        default=SourceChannel.manual_upload,
    )
    metadata_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    application: Mapped[Optional["TrademarkApplicationDraft"]] = relationship(
        back_populates="source_documents"
    )
    uploaded_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[uploaded_by_user_id]
    )
    pages: Mapped[list["DocumentPage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    extracted_fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPage(Base):
    """Текст одной страницы с указанием способа извлечения."""

    __tablename__ = "document_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(ExtractionMethod, name="extractionmethod"), nullable=False
    )
    # Заполняется только при OCR; для текстового слоя остаётся NULL,
    # чтобы не выдавать отсутствие OCR за стопроцентную уверенность.
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["SourceDocument"] = relationship(back_populates="pages")


class ExtractedField(Base):
    """Одно извлечённое поле с полной прослеживаемостью до источника."""

    __tablename__ = "extracted_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Значение, внесённое специалистом вручную, документа-источника
    # не имеет: в выписке его не было (например, адрес места
    # жительства ИП скрыт) либо поле заведено сверх маппинга.
    document_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    application_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Канонический путь поля, напр. "registry.legal_entity.inn"
    field_path: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    raw_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- прослеживаемость ---
    source_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pattern_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(ExtractionMethod, name="extractionmethod"), nullable=False
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- валидация и статус ---
    status: Mapped[FieldStatus] = mapped_column(
        Enum(FieldStatus, name="fieldstatus"),
        nullable=False,
        default=FieldStatus.needs_review,
    )
    validation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Персональные данные — маскировать в логах и не отдавать без нужды.
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped["SourceDocument"] = relationship(back_populates="extracted_fields")
    candidates: Mapped[list["FieldCandidate"]] = relationship(
        back_populates="field", cascade="all, delete-orphan"
    )
    confirmations: Mapped[list["FieldConfirmation"]] = relationship(
        back_populates="field", cascade="all, delete-orphan"
    )


class FieldCandidate(Base):
    """Один из нескольких конкурирующих вариантов значения поля.

    Если regex нашёл больше одного правдоподобного значения, все варианты
    сохраняются, поле получает статус ``conflict``/``needs_review``, и
    выбор делает специалист. Молча брать первый вариант запрещено.
    """

    __tablename__ = "field_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    field_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("extracted_fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pattern_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(ExtractionMethod, name="extractionmethod"), nullable=False
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    validation_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    field: Mapped["ExtractedField"] = relationship(back_populates="candidates")


class FieldConfirmation(Base):
    """История решений специалиста по полю: кто, что и когда изменил."""

    __tablename__ = "field_confirmations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    field_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("extracted_fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[ConfirmationAction] = mapped_column(
        Enum(ConfirmationAction, name="confirmationaction"), nullable=False
    )
    previous_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_candidate_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("field_candidates.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    field: Mapped["ExtractedField"] = relationship(back_populates="confirmations")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


# ===========================================================================
# Оценка рисков регистрации с прослеживаемостью до базы знаний
# ---------------------------------------------------------------------------
# Каждый вывод хранится вместе с цитатами, а каждая цитата — со ссылкой
# на конкретный фрагмент базы знаний и результатом его проверки.
# Это позволяет спустя время воспроизвести, на чём был основан вывод,
# и увидеть, что именно было подтверждено, а что отброшено.
# ===========================================================================

class AnalysisKind(str, enum.Enum):
    absolute_grounds = "absolute_grounds"   # ст. 1483 п. 1-4
    relative_grounds = "relative_grounds"   # ст. 1483 п. 5-10
    combined = "combined"


class SearchMode(str, enum.Enum):
    """Режим поиска по реестру — обязан быть виден в отчёте."""

    real = "real"          # полноценный поиск по реестру
    demo = "demo"          # ограниченный демонстрационный датасет
    limited = "limited"    # частичный доступ к источнику
    not_performed = "not_performed"


class CitationStatus(str, enum.Enum):
    verified = "verified"               # текст найден в источнике дословно
    partial = "partial"                 # найдена большая часть слов
    not_found = "not_found"             # в источнике такого нет
    source_missing = "source_missing"   # источника не существует
    too_short = "too_short"             # цитата слишком коротка для проверки


class RiskAssessment(Base):
    """Результат одного прогона анализа рисков."""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_kind: Mapped[AnalysisKind] = mapped_column(
        Enum(AnalysisKind, name="analysiskind"),
        nullable=False,
        default=AnalysisKind.absolute_grounds,
    )

    # --- результат ---
    overall_risk: Mapped[Optional[RiskLevel]] = mapped_column(
        Enum(RiskLevel, name="risklevel"), nullable=True
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    limitations_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    missing_data_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # Вывод не сделан: данных или источников недостаточно.
    is_inconclusive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    inconclusive_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- воспроизводимость ---
    # Без этих полей нельзя понять, на чём был основан вывод спустя время.
    knowledge_base_version: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    model_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    search_mode: Mapped[SearchMode] = mapped_column(
        Enum(SearchMode, name="searchmode"),
        nullable=False,
        default=SearchMode.not_performed,
    )
    sources_used_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    verification_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # Классы МКТУ, с учётом которых сделан вывод. Различительная
    # способность оценивается только применительно к конкретным товарам,
    # поэтому перечень классов — часть исходных данных вывода.
    classes_considered_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Подтверждены ли эти классы специалистом. Если нет, вывод сделан
    # на неподтверждённом входе.
    classes_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Признак обязателен и всегда истинен: система не даёт заключений.
    requires_specialist_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        foreign_keys=[application_id]
    )
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_user_id]
    )
    findings: Mapped[list["RiskFinding"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class RiskFinding(Base):
    """Один установленный риск с обоснованием."""

    __tablename__ = "risk_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("risk_assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="risklevel"), nullable=False
    )
    legal_basis: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    # Факты дела, на которых основан вывод.
    case_facts_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    missing_data_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Хотя бы одна цитата подтверждена дословно в источнике.
    citations_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    verification_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # Решение специалиста по выводу.
    reviewer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewer_decision: Mapped[Optional[ReviewerDecision]] = mapped_column(
        Enum(ReviewerDecision, name="reviewerdecision"), nullable=True
    )
    reviewer_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    assessment: Mapped["RiskAssessment"] = relationship(back_populates="findings")
    citations: Mapped[list["AnalysisCitation"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )
    reviewer: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[reviewer_id]
    )


class AnalysisCitation(Base):
    """Цитата из базы знаний с результатом её проверки.

    Хранится и подтверждённая, и отклонённая цитата: отклонённые нужны,
    чтобы специалист видел, что именно система не приняла и почему.
    """

    __tablename__ = "analysis_citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    finding_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("risk_findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Ссылка на конкретный фрагмент базы знаний. NULL, если модель
    # сослалась на несуществующий источник — такую цитату тоже сохраняем.
    knowledge_chunk_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("knowledge_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    source_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    anchor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[CitationStatus] = mapped_column(
        Enum(CitationStatus, name="citationstatus"), nullable=False
    )
    matched_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    finding: Mapped["RiskFinding"] = relationship(back_populates="citations")
    knowledge_chunk: Mapped[Optional["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk", foreign_keys=[knowledge_chunk_id]
    )


# ===========================================================================
# Входящие обращения
# ---------------------------------------------------------------------------
# Единая точка приёма: сейчас юрист вносит обращение вручную, позже сюда
# же встанут CRM, почта и webhook. Канал различается полем source,
# остальной путь обработки общий.
#
# Повторная доставка одного события не должна создавать дубликат дела,
# поэтому у события есть idempotency_key.
# ===========================================================================

class InboundStatus(str, enum.Enum):
    received = "received"                  # принято, ещё не обработано
    linked = "linked"                      # привязано к существующему делу
    case_created = "case_created"          # создано дело-черновик
    rejected = "rejected"                  # отклонено специалистом
    duplicate = "duplicate"                # повтор уже принятого события


class InboundEvent(Base):
    """Обращение, поступившее в систему."""

    __tablename__ = "inbound_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    source: Mapped[SourceChannel] = mapped_column(
        Enum(SourceChannel, name="sourcechannel"),
        nullable=False,
        default=SourceChannel.manual_upload,
    )
    # Идентификатор в системе-источнике: письмо, сделка CRM, вызов webhook.
    external_event_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    # Ключ идемпотентности: повтор того же события не создаёт дубликат.
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sender: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    links_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # Исходный payload сохраняется целиком и связывается с аудитом.
    raw_payload_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    status: Mapped[InboundStatus] = mapped_column(
        Enum(InboundStatus, name="inboundstatus"),
        nullable=False,
        default=InboundStatus.received,
    )
    target_case_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    target_case: Mapped[Optional["TrademarkApplicationDraft"]] = relationship(
        foreign_keys=[target_case_id]
    )
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_user_id]
    )
    attachments: Mapped[list["InboundAttachment"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class InboundAttachment(Base):
    """Связь обращения с загруженным документом."""

    __tablename__ = "inbound_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inbound_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("source_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped["InboundEvent"] = relationship(back_populates="attachments")
    document: Mapped[Optional["SourceDocument"]] = relationship(
        "SourceDocument", foreign_keys=[document_id]
    )


# ===========================================================================
# Черновик заявления
# ---------------------------------------------------------------------------
# Заполняется только подтверждёнными данными. Поле со статусом
# missing / conflict / needs_review в документ не попадает: черновик
# юридически значимого документа не должен содержать непроверенных
# значений, даже если система в них уверена.
# ===========================================================================

class DraftStatus(str, enum.Enum):
    draft = "draft"
    ready_for_review = "ready_for_review"
    approved_by_specialist = "approved_by_specialist"
    exported = "exported"


class ApplicationDraft(Base):
    """Версия чернового заявления на регистрацию товарного знака."""

    __tablename__ = "application_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trademark_application_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Номер версии в рамках дела: каждая генерация сохраняется отдельно.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, name="draftstatus"),
        nullable=False,
        default=DraftStatus.draft,
    )

    # --- содержимое ---
    # Значения, попавшие в документ: field_id -> значение.
    filled_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Поля, намеренно оставленные пустыми, с причиной.
    skipped_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Чего не хватает для подачи — чек-лист для специалиста.
    checklist_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # --- файл ---
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # --- прослеживаемость ---
    template_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    template_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mapping_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Экспорт разрешён только после утверждения специалистом.
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    application: Mapped["TrademarkApplicationDraft"] = relationship(
        foreign_keys=[application_id]
    )
    approved_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[approved_by_user_id]
    )
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_user_id]
    )
