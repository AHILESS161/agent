"""
Database initialisation and demo seed data for the Trademark Registration System.

Usage:
    python -m app.seed.init_db
    python -m app.seed.init_db --users-only

Creates all tables and populates them with realistic demo data:
- 4 users (admin, lawyer, manager, client)
- 5 clients (companies, sole proprietors, individuals)
- 8 applications in various pipeline stages
- Sample legal reviews, class suggestions, conflict results,
  recommendation memos, notifications, and audit log entries.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure we can import app modules when running as __main__
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
# Use bcrypt directly to avoid passlib 4.x + bcrypt version incompatibility in seed scripts
import bcrypt as _bcrypt_lib

def hash_password(plain: str) -> str:
    """Hash a password with bcrypt (seed-script safe, bypasses passlib version check)."""
    return _bcrypt_lib.hashpw(plain.encode("utf-8"), _bcrypt_lib.gensalt(12)).decode("utf-8")
from app.infrastructure.database.models import (
    ApplicationStatus,
    AuditLog,
    Client,
    ClientType,
    ConflictDecision,
    ConflictSearchJob,
    ConflictSearchResult,
    FindingSeverity,
    FindingType,
    GoodsServicesItem,
    ItemSource,
    LegalFinding,
    LegalReview,
    MarkType,
    NiceCategory,
    NiceClassSuggestion,
    Notification,
    NotificationType,
    RecommendationMemo,
    RecommendedAction,
    ReviewType,
    ReviewerDecision,
    RiskLevel,
    SearchJobStatus,
    TrademarkApplicationDraft,
    User,
    UserRole,
)
from app.infrastructure.database.session import Base

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Synchronous engine helper (SQLite doesn't need async for seed scripts)
# ---------------------------------------------------------------------------
def _make_sync_url(async_url: str) -> str:
    return async_url.replace("sqlite+aiosqlite:///", "sqlite:///").replace(
        "postgresql+asyncpg://", "postgresql://"
    )

def _build_sync_engine():
    sync_url = _make_sync_url(settings.DATABASE_URL)
    connect_args = {}
    if sync_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(sync_url, echo=False, connect_args=connect_args)


# ---------------------------------------------------------------------------
# Helper: offset-aware UTC datetime
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _ago(days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    return _now() - timedelta(days=days, hours=hours, minutes=minutes)


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_users(session: Session) -> dict[str, User]:
    """Create demo users and return the primary account for every role."""
    users_data = [
        {
            "email": "admin@demo.ru",
            "full_name": "Администратор Системы",
            "role": UserRole.admin,
            "password": "demo123",
        },
        {
            "email": "lawyer@demo.ru",
            "full_name": "Иванова Елена Викторовна",
            "role": UserRole.lawyer,
            "password": "demo123",
        },
        {
            "email": "bogdan@demo.ru",
            "full_name": "Богдан",
            "role": UserRole.lawyer,
            "password": "demo123",
        },
        {
            "email": "dasha@demo.ru",
            "full_name": "Дарья (Даша)",
            "role": UserRole.lawyer,
            "password": "demo123",
        },
        {
            "email": "manager@demo.ru",
            "full_name": "Петров Сергей Александрович",
            "role": UserRole.manager,
            "password": "demo123",
        },
        {
            "email": "client@demo.ru",
            "full_name": "Козлов Дмитрий Игоревич",
            "role": UserRole.client,
            "password": "demo123",
        },
    ]

    result: dict[str, User] = {}
    for data in users_data:
        existing = session.query(User).filter_by(email=data["email"]).first()
        if existing:
            log.info(f"  User {data['email']} already exists — skipping")
            result.setdefault(data["role"].value, existing)
            continue

        user = User(
            email=data["email"],
            full_name=data["full_name"],
            hashed_password=hash_password(data["password"]),
            role=data["role"],
            is_active=True,
        )
        session.add(user)
        result.setdefault(data["role"].value, user)
        log.info(f"  Created user: {data['email']} ({data['role'].value})")

    session.flush()
    return result


def seed_clients(session: Session) -> list[Client]:
    """Create 5 demo clients."""
    clients_data = [
        {
            "full_name_or_company_name": 'ООО "ТехноСфера"',
            "short_name": "ТехноСфера",
            "type": ClientType.company,
            "inn": "7701234567",
            "ogrn_or_ogrnip": "1177746123456",
            "address": "127006, г. Москва, ул. Тверская, д. 15, офис 301",
            "email": "info@technosfera.ru",
            "phone": "+7 (495) 123-45-67",
            "country": "RU",
        },
        {
            "full_name_or_company_name": "ИП Иванов Алексей Андреевич",
            "short_name": "ИП Иванов А.А.",
            "type": ClientType.sole_proprietor,
            "inn": "773456789012",
            "ogrn_or_ogrnip": "318774600312345",
            "address": "115093, г. Москва, ул. Большая Серпуховская, д. 44, кв. 12",
            "email": "ivanov.aa@mail.ru",
            "phone": "+7 (916) 234-56-78",
            "country": "RU",
        },
        {
            "full_name_or_company_name": 'ООО "Зелёный Мир"',
            "short_name": "Зелёный Мир",
            "type": ClientType.company,
            "inn": "7703456789",
            "ogrn_or_ogrnip": "1177703456789",
            "address": "107078, г. Москва, ул. Новая Басманная, д. 21, стр. 1",
            "email": "contact@greenworld.ru",
            "phone": "+7 (495) 345-67-89",
            "country": "RU",
        },
        {
            "full_name_or_company_name": 'АО "Цифровые Решения"',
            "short_name": "Цифровые Решения",
            "type": ClientType.company,
            "inn": "7705678901",
            "ogrn_or_ogrnip": "1187746789012",
            "address": "121205, г. Москва, территория инновационного центра Сколково, Большой бульвар, д. 42, стр. 1",
            "email": "legal@digisol.ru",
            "phone": "+7 (495) 678-90-12",
            "country": "RU",
        },
        {
            "full_name_or_company_name": "Петрова Мария Сергеевна",
            "short_name": "Петрова М.С.",
            "type": ClientType.individual,
            "inn": "771234567890",
            "ogrn_or_ogrnip": None,
            "address": "109147, г. Москва, ул. Марксистская, д. 3, кв. 47",
            "email": "m.petrova@gmail.com",
            "phone": "+7 (926) 789-01-23",
            "country": "RU",
        },
    ]

    clients: list[Client] = []
    for data in clients_data:
        existing = session.query(Client).filter_by(
            full_name_or_company_name=data["full_name_or_company_name"]
        ).first()
        if existing:
            log.info(f"  Client {data['short_name']} already exists — skipping")
            clients.append(existing)
            continue

        client = Client(
            full_name_or_company_name=data["full_name_or_company_name"],
            short_name=data["short_name"],
            type=data["type"],
            inn=data["inn"],
            ogrn_or_ogrnip=data.get("ogrn_or_ogrnip"),
            address=data["address"],
            email=data["email"],
            phone=data["phone"],
            country=data.get("country", "RU"),
        )
        session.add(client)
        clients.append(client)
        log.info(f"  Created client: {data['short_name']} ({data['type'].value})")

    session.flush()
    return clients


def seed_applications(
    session: Session,
    clients: list[Client],
    users: dict[str, User],
) -> list[TrademarkApplicationDraft]:
    """Create 8 demo applications in various pipeline stages."""
    lawyer = users["lawyer"]
    manager = users["manager"]

    techno, ivanov, green, digital, petrova = clients

    apps_data = [
        # 1 — draft
        {
            "mark_name": "ТехноСфера",
            "mark_text": "ТехноСфера",
            "mark_type": MarkType.word,
            "status": ApplicationStatus.draft,
            "client": techno,
            "lawyer": None,
            "manager_user": manager,
            "business_description": "Программное обеспечение для управления производством",
            "goods_services_raw": "Программное обеспечение; SaaS-платформы; консультационные услуги в области ИТ",
            "created_at": _ago(days=7),
            "updated_at": _ago(days=7),
        },
        # 2 — info_requested (missing image for figurative mark)
        {
            "mark_name": "ЭкоЛайф",
            "mark_text": "ЭкоЛайф",
            "mark_type": MarkType.figurative,
            "status": ApplicationStatus.info_requested,
            "client": green,
            "lawyer": None,
            "manager_user": manager,
            "business_description": "Экологически чистые продукты питания",
            "goods_services_raw": "Продукты питания органического происхождения; напитки безалкогольные",
            "created_at": _ago(days=14),
            "updated_at": _ago(days=12),
        },
        # 3 — legal_review_done
        {
            "mark_name": "ЦИФРА+",
            "mark_text": "ЦИФРА+",
            "mark_type": MarkType.combined,
            "status": ApplicationStatus.legal_review_done,
            "client": digital,
            "lawyer": lawyer,
            "manager_user": manager,
            "business_description": "Финансовые технологии и платёжные системы",
            "goods_services_raw": "Финансовые услуги; электронные платёжные системы; мобильные приложения для банкинга",
            "created_at": _ago(days=21),
            "updated_at": _ago(days=3),
        },
        # 4 — classification_review
        {
            "mark_name": "ЗелёныйДом",
            "mark_text": "ЗелёныйДом",
            "mark_type": MarkType.word,
            "status": ApplicationStatus.classification_review,
            "client": green,
            "lawyer": None,
            "manager_user": manager,
            "business_description": "Строительные материалы из переработанного сырья",
            "goods_services_raw": "Строительные материалы; экологически чистые лакокрасочные покрытия; услуги по экодизайну",
            "created_at": _ago(days=10),
            "updated_at": _ago(days=2),
        },
        # 5 — conflict_search_in_progress
        {
            "mark_name": "НОВА",
            "mark_text": "НОВА",
            "mark_type": MarkType.word,
            "status": ApplicationStatus.conflict_search_in_progress,
            "client": petrova,
            "lawyer": lawyer,
            "manager_user": manager,
            "business_description": "Косметика и средства по уходу за кожей",
            "goods_services_raw": "Косметические средства; средства по уходу за волосами; парфюмерия",
            "created_at": _ago(days=18),
            "updated_at": _ago(hours=6),
        },
        # 6 — memo_approved
        {
            "mark_name": "АльфаТек",
            "mark_text": "АльфаТек",
            "mark_type": MarkType.word,
            "status": ApplicationStatus.memo_approved,
            "client": ivanov,
            "lawyer": lawyer,
            "manager_user": manager,
            "business_description": "Промышленное оборудование и автоматизация",
            "goods_services_raw": "Промышленные роботы; станки с ЧПУ; услуги по автоматизации производства",
            "created_at": _ago(days=30),
            "updated_at": _ago(days=1),
        },
        # 7 — submitted
        {
            "mark_name": "БРИЗ",
            "mark_text": "БРИЗ",
            "mark_type": MarkType.word,
            "status": ApplicationStatus.submitted,
            "client": techno,
            "lawyer": lawyer,
            "manager_user": manager,
            "business_description": "Кондиционирование воздуха и вентиляция",
            "goods_services_raw": "Системы кондиционирования воздуха; вентиляционное оборудование; монтажные услуги",
            "created_at": _ago(days=60),
            "updated_at": _ago(days=5),
            "notes": "Номер заявки в Роспатенте: 2024123456",
        },
        # 8 — closed (rejected)
        {
            "mark_name": "КВАНТ",
            "mark_text": "КВАНТ",
            "mark_type": MarkType.word,
            "status": ApplicationStatus.closed,
            "client": digital,
            "lawyer": lawyer,
            "manager_user": manager,
            "business_description": "Квантовые вычисления",
            "goods_services_raw": "Квантовые компьютеры; программное обеспечение для квантовых вычислений",
            "created_at": _ago(days=90),
            "updated_at": _ago(days=15),
            "notes": "Отказано: обозначение 'КВАНТ' лишено различительной способности (ст.1483 п.1 ГК РФ)",
        },
    ]

    apps: list[TrademarkApplicationDraft] = []
    for data in apps_data:
        existing = session.query(TrademarkApplicationDraft).filter_by(
            mark_name=data["mark_name"]
        ).first()
        if existing:
            log.info(f"  Application {data['mark_name']} already exists — skipping")
            apps.append(existing)
            continue

        app = TrademarkApplicationDraft(
            client_id=data["client"].id,
            assigned_lawyer_id=data["lawyer"].id if data.get("lawyer") else None,
            assigned_manager_id=data["manager_user"].id if data.get("manager_user") else None,
            mark_name=data["mark_name"],
            mark_text=data.get("mark_text"),
            mark_type=data["mark_type"],
            status=data["status"],
            business_description=data.get("business_description"),
            goods_services_raw=data.get("goods_services_raw"),
            notes=data.get("notes"),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
        )
        session.add(app)
        apps.append(app)
        log.info(f"  Created application: {data['mark_name']} (status={data['status'].value})")

    session.flush()
    return apps


def seed_nice_class_suggestions(
    session: Session,
    apps: list[TrademarkApplicationDraft],
) -> None:
    """Seed NICE class suggestions for applications in classification stages."""
    # App index 3 = ЗелёныйДом (classification_review)
    greendom_app = apps[3]

    suggestions = [
        NiceClassSuggestion(
            application_id=greendom_app.id,
            class_number=19,
            class_description="Строительные материалы (не из металла); трубы (не металлические) для строительства",
            confidence=0.92,
            category=NiceCategory.primary,
            rationale="Описание товаров прямо соответствует классу 19 МКТУ — строительные материалы.",
        ),
        NiceClassSuggestion(
            application_id=greendom_app.id,
            class_number=2,
            class_description="Краски, лаки, олифа; средства для сохранения дерева; красители",
            confidence=0.85,
            category=NiceCategory.primary,
            rationale="Лакокрасочные покрытия относятся к классу 2 МКТУ.",
        ),
        NiceClassSuggestion(
            application_id=greendom_app.id,
            class_number=42,
            class_description="Научные и технологические услуги и исследования; промышленный дизайн",
            confidence=0.78,
            category=NiceCategory.secondary,
            rationale="Услуги по экодизайну относятся к классу 42.",
        ),
    ]

    # App index 0 = ТехноСфера (draft) — pre-seeded classes
    techno_app = apps[0]
    suggestions += [
        NiceClassSuggestion(
            application_id=techno_app.id,
            class_number=42,
            class_description="Разработка программного обеспечения; SaaS-услуги; ИТ-консультирование",
            confidence=0.96,
            category=NiceCategory.primary,
            rationale="Основной вид деятельности — разработка ПО и SaaS, класс 42.",
        ),
        NiceClassSuggestion(
            application_id=techno_app.id,
            class_number=9,
            class_description="Компьютерное программное обеспечение; приборы для обработки информации",
            confidence=0.89,
            category=NiceCategory.secondary,
            rationale="Программный продукт как товар относится к классу 9.",
        ),
    ]

    for s in suggestions:
        session.add(s)

    log.info(f"  Created {len(suggestions)} NICE class suggestions")


def seed_goods_services(
    session: Session,
    apps: list[TrademarkApplicationDraft],
) -> None:
    """Seed GoodsServicesItem records for applications further in the pipeline."""
    # App 2 = ЦИФРА+ (legal_review_done) — confirmed classes
    cifra_app = apps[2]
    items = [
        GoodsServicesItem(
            application_id=cifra_app.id,
            raw_text="Финансовые услуги; электронные платёжные системы",
            proposed_class=36,
            approved_class=36,
            source=ItemSource.ai,
        ),
        GoodsServicesItem(
            application_id=cifra_app.id,
            raw_text="Мобильные приложения для банкинга; программное обеспечение",
            proposed_class=42,
            approved_class=42,
            source=ItemSource.ai,
        ),
    ]
    for item in items:
        session.add(item)

    # App 5 = АльфаТек (memo_approved) — confirmed classes
    alphatek_app = apps[5]
    items2 = [
        GoodsServicesItem(
            application_id=alphatek_app.id,
            raw_text="Промышленные роботы; станки с числовым программным управлением",
            proposed_class=7,
            approved_class=7,
            source=ItemSource.ai,
        ),
        GoodsServicesItem(
            application_id=alphatek_app.id,
            raw_text="Услуги по автоматизации производства; промышленный инжиниринг",
            proposed_class=42,
            approved_class=42,
            source=ItemSource.ai,
        ),
    ]
    for item in items2:
        session.add(item)

    log.info("  Created goods/services items")


def seed_legal_reviews(
    session: Session,
    apps: list[TrademarkApplicationDraft],
    users: dict[str, User],
) -> None:
    """Seed legal reviews for applications that have passed legal review stage."""
    lawyer = users["lawyer"]

    # App 2 = ЦИФРА+ (legal_review_done)
    cifra_app = apps[2]
    review = LegalReview(
        application_id=cifra_app.id,
        reviewer_id=lawyer.id,
        review_type=ReviewType.combined,
        risk_level=RiskLevel.medium,
        reviewer_decision=ReviewerDecision.approve,
        absolute_grounds_summary=(
            "Обозначение «ЦИФРА+» обладает достаточной различительной способностью. "
            "Слово «ЦИФРА» является описательным для услуг в сфере финансовых технологий "
            "(класс 36), однако добавление знака «+» создаёт необходимую оригинальность."
        ),
        relative_grounds_summary=(
            "Поиск конфликтующих обозначений не выявил тождественных знаков. "
            "Рекомендуется подача с указанием на фантазийный характер обозначения."
        ),
        confidence_score=0.72,
        created_at=_ago(days=5),
    )
    session.add(review)
    session.flush()

    # Findings for ЦИФРА+
    finding = LegalFinding(
        legal_review_id=review.id,
        finding_type=FindingType.absolute,
        severity=FindingSeverity.warning,
        ground_article="ГК РФ ст. 1483 п. 1",
        description=(
            "Элемент «ЦИФРА» носит описательный характер применительно к "
            "услугам по классу 36 (финансовые услуги, платёжные системы)."
        ),
        confidence=0.70,
    )
    session.add(finding)

    # App 5 = АльфаТек (memo_approved) — clean legal review
    alpha_app = apps[5]
    review2 = LegalReview(
        application_id=alpha_app.id,
        reviewer_id=lawyer.id,
        review_type=ReviewType.combined,
        risk_level=RiskLevel.low,
        reviewer_decision=ReviewerDecision.approve,
        absolute_grounds_summary=(
            "Обозначение «АльфаТек» является фантазийным, обладает высокой "
            "различительной способностью. Абсолютных оснований для отказа не выявлено."
        ),
        relative_grounds_summary=(
            "Поиск по базе ФИПС не выявил тождественных знаков в классах 7 и 42. "
            "Частичное совпадение с «АЛЬФАТЕХ» (рег. № 789012) не является конфликтом."
        ),
        confidence_score=0.93,
        created_at=_ago(days=20),
    )
    session.add(review2)

    log.info("  Created legal reviews and findings")


def seed_conflict_results(
    session: Session,
    apps: list[TrademarkApplicationDraft],
) -> None:
    """Seed conflict search jobs and results."""
    # App 4 = НОВА (conflict_search_in_progress)
    nova_app = apps[4]
    job = ConflictSearchJob(
        application_id=nova_app.id,
        status=SearchJobStatus.running,
        provider="mock_fips",
        search_strategy_json={
            "mark_text": "НОВА",
            "classes": [3],
            "phonetic_variants": ["NOVA", "НОВА", "НОВА"],
        },
        started_at=_ago(hours=5, minutes=55),
    )
    session.add(job)

    # App 5 = АльфаТек (memo_approved) — completed conflict search
    alpha_app = apps[5]
    job2 = ConflictSearchJob(
        application_id=alpha_app.id,
        status=SearchJobStatus.completed,
        provider="mock_fips",
        search_strategy_json={
            "mark_text": "АльфаТек",
            "classes": [7, 42],
            "phonetic_variants": ["ALFATEK", "АльфаТек", "ALPHATEK"],
        },
        started_at=_ago(days=22),
        completed_at=_ago(days=21),
        total_results=1,
    )
    session.add(job2)
    session.flush()

    # One result for АльфаТек job — no conflict
    result = ConflictSearchResult(
        search_job_id=job2.id,
        application_id=alpha_app.id,
        matched_mark="АЛЬФАТЕХ",
        owner='ООО "АльфаТехнологии"',
        classes=[7],
        similarity_score=0.41,
        phonetic_score=0.55,
        reviewer_decision=ConflictDecision.no_conflict,
        conflict_reason=(
            "Знак «АЛЬФАТЕХ» частично совпадает по звучанию, однако зарегистрирован "
            "только в классе 7. При регистрации заявителя также в классе 42 конфликт "
            "не возникает. Визуальное и концептуальное сходство ниже порогового."
        ),
        provider="mock_fips",
    )
    session.add(result)

    log.info("  Created conflict search jobs and results")


def seed_recommendations(
    session: Session,
    apps: list[TrademarkApplicationDraft],
    users: dict[str, User],
) -> None:
    """Seed recommendation memos for apps at memo stage."""
    lawyer = users["lawyer"]

    # App 5 = АльфаТек (memo_approved)
    alpha_app = apps[5]
    memo = RecommendationMemo(
        application_id=alpha_app.id,
        recommended_action=RecommendedAction.proceed,
        risk_assessment=(
            "Уровень риска: НИЗКИЙ. Обозначение «АльфаТек» является фантазийным, "
            "обладает высокой различительной способностью. Конфликтующих знаков не обнаружено. "
            "Поиск охватил 47 знаков в классах 7 и 42."
        ),
        summary=(
            "На основании правовой экспертизы и поиска конфликтов рекомендуется подача "
            "заявки на регистрацию товарного знака «АльфаТек» в классах МКТУ 7 и 42. "
            "Ожидаемый срок регистрации — 18 месяцев. Государственная пошлина: 33 000 руб."
        ),
        recommended_classes_json=[7, 42],
        confidence=0.91,
        approved_by=lawyer.id,
        approved_at=_ago(days=1),
    )
    session.add(memo)
    log.info("  Created recommendation memos")


def seed_notifications(
    session: Session,
    apps: list[TrademarkApplicationDraft],
    users: dict[str, User],
) -> None:
    """Seed notification records."""
    manager = users["manager"]
    lawyer = users["lawyer"]

    notifications = [
        Notification(
            user_id=manager.id,
            application_id=apps[1].id,  # ЭкоЛайф
            type=NotificationType.action_required,
            title="Требуется дополнительная информация по заявке «ЭкоЛайф»",
            message=(
                "Для продолжения обработки заявки необходимо предоставить изображение "
                "товарного знака в формате PNG/SVG с разрешением не менее 300 dpi. "
                "Пожалуйста, загрузите файл через личный кабинет."
            ),
            is_read=False,
            created_at=_ago(days=12),
        ),
        Notification(
            user_id=lawyer.id,
            application_id=apps[2].id,  # ЦИФРА+
            type=NotificationType.action_required,
            title="Заявка «ЦИФРА+» готова к правовой экспертизе",
            message=(
                "Заявка прошла классификацию МКТУ (классы 36, 42) и передана на "
                "правовую экспертизу. Срок: 5 рабочих дней."
            ),
            is_read=True,
            created_at=_ago(days=8),
        ),
        Notification(
            user_id=manager.id,
            application_id=apps[5].id,  # АльфаТек
            type=NotificationType.status_change,
            title="Меморандум по заявке «АльфаТек» утверждён",
            message=(
                "Юрист Иванова Е.В. утвердила меморандум с рекомендацией ПОДАТЬ ЗАЯВКУ. "
                "Риск регистрации: НИЗКИЙ. Заявку можно передавать клиенту для согласования."
            ),
            is_read=False,
            created_at=_ago(days=1),
        ),
        Notification(
            user_id=manager.id,
            application_id=apps[6].id,  # БРИЗ
            type=NotificationType.status_change,
            title="Заявка «БРИЗ» подана в Роспатент",
            message=(
                "Заявка успешно подана в Роспатент. Номер заявки: 2024123456. "
                "Ожидаемый срок формальной экспертизы — 1 месяц."
            ),
            is_read=True,
            created_at=_ago(days=5),
        ),
    ]

    for notif in notifications:
        session.add(notif)

    log.info(f"  Created {len(notifications)} notifications")


def seed_audit_log(
    session: Session,
    apps: list[TrademarkApplicationDraft],
    users: dict[str, User],
) -> None:
    """Seed audit log entries for key events."""
    admin = users["admin"]
    manager = users["manager"]
    lawyer = users["lawyer"]

    entries = [
        # User registration
        AuditLog(
            user_id=admin.id,
            application_id=None,
            action="user.created",
            entity_type="User",
            entity_id=str(manager.id),
            new_value_json={"email": manager.email, "role": manager.role.value},
            ip_address="127.0.0.1",
            created_at=_ago(days=30),
        ),
        # Application created
        AuditLog(
            user_id=manager.id,
            application_id=apps[0].id,
            action="application.created",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(apps[0].id),
            new_value_json={"mark_name": "ТехноСфера", "status": "draft"},
            ip_address="192.168.1.10",
            created_at=_ago(days=7),
        ),
        # Status transitions for ЦИФРА+
        AuditLog(
            user_id=manager.id,
            application_id=apps[2].id,
            action="application.status_changed",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(apps[2].id),
            old_value_json={"status": "classification_approved"},
            new_value_json={"status": "legal_review_pending"},
            ip_address="192.168.1.10",
            created_at=_ago(days=10),
        ),
        AuditLog(
            user_id=lawyer.id,
            application_id=apps[2].id,
            action="application.status_changed",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(apps[2].id),
            old_value_json={"status": "legal_review_in_progress"},
            new_value_json={"status": "legal_review_done"},
            ip_address="10.0.0.5",
            created_at=_ago(days=3),
        ),
        # Legal review approved for АльфаТек
        AuditLog(
            user_id=lawyer.id,
            application_id=apps[5].id,
            action="legal_review.completed",
            entity_type="LegalReview",
            entity_id="2",
            new_value_json={"risk_level": "low", "decision": "approve"},
            ip_address="10.0.0.5",
            created_at=_ago(days=18),
        ),
        # Memo approved for АльфаТек
        AuditLog(
            user_id=lawyer.id,
            application_id=apps[5].id,
            action="memo.approved",
            entity_type="RecommendationMemo",
            entity_id="1",
            new_value_json={"recommended_action": "proceed"},
            ip_address="10.0.0.5",
            created_at=_ago(days=1),
        ),
        # Submission of БРИЗ
        AuditLog(
            user_id=lawyer.id,
            application_id=apps[6].id,
            action="application.submitted",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(apps[6].id),
            new_value_json={
                "status": "submitted",
                "submitted_at": _ago(days=5).isoformat(),
            },
            ip_address="10.0.0.5",
            created_at=_ago(days=5),
        ),
        # Closure of КВАНТ
        AuditLog(
            user_id=lawyer.id,
            application_id=apps[7].id,
            action="application.closed",
            entity_type="TrademarkApplicationDraft",
            entity_id=str(apps[7].id),
            old_value_json={"status": "legal_review_done"},
            new_value_json={
                "status": "closed",
                "reason": "Обозначение 'КВАНТ' лишено различительной способности (ГК РФ ст.1483 п.1)",
            },
            ip_address="10.0.0.5",
            created_at=_ago(days=15),
        ),
    ]

    for entry in entries:
        session.add(entry)

    log.info(f"  Created {len(entries)} audit log entries")


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare demo data")
    parser.add_argument(
        "--users-only",
        action="store_true",
        help="Create demo accounts without adding sample clients and applications",
    )
    args = parser.parse_args()
    log.info(
        "=== Initialising database and seeding demo accounts ==="
        if args.users_only
        else "=== Initialising database and seeding demo data ==="
    )

    engine = _build_sync_engine()

    # Схему создают миграции Alembic, а не этот скрипт: create_all()
    # не версионируется и со временем расходится с миграциями.
    if not inspect(engine).has_table("alembic_version"):
        raise SystemExit(
            "Схема БД не инициализирована. Сначала выполните:\n"
            "    alembic upgrade head"
        )
    log.info("  Схема БД проверена (миграции применены)")

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        try:
            log.info("\nSeeding users...")
            users = seed_users(session)

            if not args.users_only:
                log.info("\nSeeding clients...")
                clients = seed_clients(session)

                log.info("\nSeeding applications...")
                apps = seed_applications(session, clients, users)

                log.info("\nSeeding NICE class suggestions...")
                seed_nice_class_suggestions(session, apps)

                log.info("\nSeeding goods/services items...")
                seed_goods_services(session, apps)

                log.info("\nSeeding legal reviews...")
                seed_legal_reviews(session, apps, users)

                log.info("\nSeeding conflict search results...")
                seed_conflict_results(session, apps)

                log.info("\nSeeding recommendation memos...")
                seed_recommendations(session, apps, users)

                log.info("\nSeeding notifications...")
                seed_notifications(session, apps, users)

                log.info("\nSeeding audit log...")
                seed_audit_log(session, apps, users)

            session.commit()
            log.info("\n✓ Database seeded successfully!")
            log.info("\nDemo credentials:")
            log.info("  admin@demo.ru   / demo123  (Администратор)")
            log.info("  lawyer@demo.ru  / demo123  (Юрист)")
            log.info("  bogdan@demo.ru  / demo123  (Юрист Богдан)")
            log.info("  dasha@demo.ru   / demo123  (Юрист Даша)")
            log.info("  manager@demo.ru / demo123  (Менеджер)")
            log.info("  client@demo.ru  / demo123  (Клиент)")

        except Exception as exc:
            session.rollback()
            log.error(f"Seeding failed: {exc}")
            raise


if __name__ == "__main__":
    main()
