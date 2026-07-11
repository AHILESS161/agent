# Система регистрации товарных знаков РФ

Автоматизированная система сопровождения регистрации товарных знаков в Роспатенте с использованием мультиагентного ИИ на базе LangGraph.

---

## Содержание

- [Описание](#описание)
- [Архитектура](#архитектура)
- [Стек технологий](#стек-технологий)
- [Быстрый старт](#быстрый-старт)
- [Структура проекта](#структура-проекта)
- [API документация](#api-документация)
- [Агентная архитектура](#агентная-архитектура)
- [Статус модулей](#статус-модулей)
- [Переменные окружения](#переменные-окружения)
- [Документация](#документация)

---

## Описание

Система автоматизирует весь жизненный цикл заявки на регистрацию товарного знака:

- **Приём заявки** — нормализация данных, проверка полноты через 18 правил
- **Классификация по МКТУ** — ИИ-агент предлагает классы, юрист утверждает
- **Правовая экспертиза** — проверка абсолютных и относительных оснований для отказа (ГК РФ ч.IV, ст.1483)
- **Поиск конфликтов** — интеграция с базой данных ФИПС (в MVP — mock-провайдер)
- **Генерация документов** — автоматическое формирование заявления, писем, меморандумов
- **Уведомления** — клиент и команда получают актуальный статус на каждом этапе

Система спроектирована как **модульный монолит** с чёткими границами поддоменов, что позволяет легко выделять отдельные сервисы при масштабировании.

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                   Модульный монолит                          │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Intake  │→ │  Class.  │→ │  Legal   │→ │Conflicts │   │
│  │  Agent   │  │  Agent   │  │  Agents  │  │  Agent   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│        ↓              ↓             ↓             ↓         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            ApplicationStateMachine (18 states)        │  │
│  └──────────────────────────────────────────────────────┘  │
│        ↓              ↓             ↓             ↓         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Docs    │  │  Human   │  │  Status  │  │Recommend.│   │
│  │  Agent   │  │  Review  │  │ Monitor  │  │  Agent   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────────────────┐    │
│  │  RAG Pipeline    │  │  LLM Provider (Ollama/OpenAI) │    │
│  │  (TF-IDF/BM25)   │  │  + Prompt Registry (YAML)    │    │
│  └──────────────────┘  └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              ↑
              FastAPI REST API (v1) + WebSocket
                              ↑
              React + Vite + shadcn/ui Frontend
```

### Bounded Contexts (18)

| # | Контекст | Описание |
|---|----------|----------|
| 1 | Identity & Access | Пользователи, роли, JWT |
| 2 | Client Management | Клиенты, представители |
| 3 | Application Intake | Приём и нормализация заявок |
| 4 | Completeness Validation | 18 правил полноты |
| 5 | NICE Classification | Классификация товаров/услуг |
| 6 | Legal Review | Абсолютные и относительные основания |
| 7 | Conflict Search | Поиск конфликтующих знаков (ФИПС) |
| 8 | Human Review | Пакет для юриста |
| 9 | Recommendations | Рекомендации и мемо |
| 10 | Document Generation | Заявление, письма, доверенность |
| 11 | Document Approval | Согласование документов |
| 12 | Submission | Подача в Роспатент |
| 13 | Status Tracking | Мониторинг статуса после подачи |
| 14 | Notifications | Email/push-уведомления |
| 15 | Audit & Compliance | Журнал всех действий |
| 16 | Knowledge Base | RAG для нормативных документов |
| 17 | Prompt Management | Реестр промптов с версионированием |
| 18 | Background Jobs | Асинхронные задачи |

### AI-агенты (13)

| Агент | Файл | Функция |
|-------|------|---------|
| IntakeValidator | agents/intake/validator.py | Первичная валидация |
| IntakeNormalizer | agents/intake/normalizer.py | Нормализация данных |
| NiceClassifier | agents/classification/nice_classifier.py | МКТУ-классификация |
| AbsoluteGroundsReviewer | agents/legal/absolute_grounds.py | Ст. 1483 п.1-4 |
| RelativeGroundsReviewer | agents/legal/relative_grounds.py | Ст. 1483 п.6 |
| ConflictQueryBuilder | agents/conflicts/query_builder.py | Построение запросов ФИПС |
| ConflictAnalyzer | agents/conflicts/analyzer.py | Анализ результатов |
| ConflictOrchestrator | agents/conflicts/orchestrator.py | Оркестрация поиска |
| HumanReviewPackager | agents/human_review/packager.py | Пакет для юриста |
| Recommender | agents/recommendations/recommender.py | Итоговые рекомендации |
| DocumentAssembler | agents/documents/assembler.py | Сборка документов |
| StatusMonitor | agents/status/monitor.py | Мониторинг после подачи |
| Submitter | agents/submission/submitter.py | Подача в ФИПС |

---

## Стек технологий

| Слой | Технологии |
|------|------------|
| **Backend** | Python 3.12, FastAPI 0.111, SQLAlchemy 2.0 (async), LangGraph, Alembic |
| **LLM** | LangGraph, Ollama (qwen2.5), OpenAI-compatible API, Mock-провайдер |
| **Frontend** | React 18, Vite, shadcn/ui, Tailwind CSS, TanStack Query |
| **БД** | SQLite (разработка) → PostgreSQL (production) |
| **Очередь** | Redis (опционально, для фоновых задач) |
| **RAG** | TF-IDF/BM25 (MVP) → pgvector / Qdrant (production) |
| **Документы** | python-docx, docxtpl |
| **Аутентификация** | JWT (python-jose), passlib[bcrypt] |
| **Контейнеризация** | Docker, Docker Compose |
| **Тестирование** | pytest, httpx, pytest-asyncio |

---

## Быстрый старт

### Предварительные требования

- Python 3.12+
- Node.js 20+
- (Опционально) Docker & Docker Compose

### Без Docker

```bash
# Клонировать репозиторий
git clone <repo-url>
cd trademark-system

# Backend
cd backend
pip install -r requirements.txt

# Скопировать конфигурацию
cp ../.env.example .env

# Инициализировать БД и загрузить тестовые данные
python -m app.seed.init_db

# Запустить сервер
uvicorn app.main:app --reload --port 8000

# Frontend (в новом терминале)
cd ../frontend
npm install
npm run dev
```

### С Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Сервисы:
- API: http://localhost:8000
- Frontend: http://localhost:3000
- API документация: http://localhost:8000/docs

### Тестовые учётные данные

| Логин | Пароль | Роль |
|-------|--------|------|
| admin@demo.ru | demo123 | Администратор |
| lawyer@demo.ru | demo123 | Юрист |
| manager@demo.ru | demo123 | Менеджер |
| client@demo.ru | demo123 | Клиент |

---

## Структура проекта

```
trademark-system/
├── README.md                          # Этот файл
├── docker-compose.yml                 # Оркестрация контейнеров
├── .env.example                       # Шаблон переменных окружения
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py                    # FastAPI application entry point
│   │   ├── core/
│   │   │   ├── config.py              # Настройки (pydantic-settings)
│   │   │   ├── security.py            # JWT, bcrypt
│   │   │   ├── exceptions.py          # Доменные исключения
│   │   │   └── logging.py             # Структурированное логирование
│   │   ├── api/v1/
│   │   │   ├── router.py              # Корневой роутер
│   │   │   └── endpoints/             # auth, clients, applications, ...
│   │   ├── agents/                    # 13 AI-агентов
│   │   │   ├── base.py
│   │   │   ├── intake/
│   │   │   ├── classification/
│   │   │   ├── legal/
│   │   │   ├── conflicts/
│   │   │   ├── human_review/
│   │   │   ├── recommendations/
│   │   │   ├── documents/
│   │   │   ├── status/
│   │   │   └── submission/
│   │   ├── services/
│   │   │   ├── completeness_engine.py # 18 правил полноты
│   │   │   ├── state_machine.py       # 18 состояний заявки
│   │   │   └── document_generator.py  # Генерация DOCX
│   │   ├── infrastructure/
│   │   │   ├── database/
│   │   │   │   ├── models.py          # SQLAlchemy ORM
│   │   │   │   └── session.py         # Async engine
│   │   │   ├── llm/
│   │   │   │   ├── base.py
│   │   │   │   ├── factory.py
│   │   │   │   ├── mock_provider.py
│   │   │   │   ├── openai_compatible_provider.py
│   │   │   │   └── prompt_registry.py
│   │   │   ├── providers/             # ФИПС, внешние API
│   │   │   └── rag/
│   │   │       ├── pipeline.py        # RAG pipeline (BM25)
│   │   │       └── knowledge_loader.py
│   │   ├── schemas/                   # Pydantic schemas
│   │   └── seed/
│   │       └── init_db.py             # Инициализация БД и демо-данных
│   ├── prompts/                       # YAML промпты (версионированные)
│   │   ├── intake/
│   │   ├── classes/
│   │   ├── legal/
│   │   ├── conflicts/
│   │   ├── recommendations/
│   │   ├── notifications/
│   │   └── docs/
│   ├── knowledge/                     # База знаний для RAG
│   │   ├── gk_rf_part4_trademarks.md
│   │   ├── rospatent_guidelines.md
│   │   └── nice_classification_overview.md
│   ├── templates/                     # Шаблоны документов
│   │   └── README.md
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       ├── api/
│       └── e2e/
│
├── frontend/
│   ├── Dockerfile
│   ├── client/src/
│   │   ├── pages/                     # dashboard, applications, clients, ...
│   │   ├── components/ui/             # shadcn/ui компоненты
│   │   └── lib/                       # auth, queryClient, utils
│   └── ...
│
└── docs/
    ├── architecture.md
    ├── domain-model.md
    ├── state-machine.md
    ├── agent-graph.md
    ├── api-contracts.md
    ├── document-pipeline.md
    ├── rag-design.md
    ├── prompt-registry.md
    ├── security.md
    └── testing-strategy.md
```

---

## API документация

После запуска бэкенда документация доступна по адресам:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Основные эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | /api/v1/auth/register | Регистрация пользователя |
| POST | /api/v1/auth/login | Вход (получение JWT) |
| GET | /api/v1/applications | Список заявок |
| POST | /api/v1/applications | Создание заявки |
| GET | /api/v1/applications/{id} | Детали заявки |
| POST | /api/v1/applications/{id}/transition | Смена статуса |
| GET | /api/v1/clients | Список клиентов |
| GET | /api/v1/notifications | Уведомления пользователя |
| GET | /api/v1/audit | Журнал аудита |
| GET | /api/v1/health | Проверка состояния |

Подробные контракты: [docs/api-contracts.md](docs/api-contracts.md)

---

## Агентная архитектура

Агенты построены на основе **LangGraph** и обмениваются состоянием через общий граф. Каждый агент:

1. Получает входные данные из состояния заявки
2. Вызывает LLM через `PromptRegistry` (YAML-промпты с версионированием)
3. Записывает результат в БД
4. Логирует в `AgentRun` (модель наблюдаемости)
5. Обновляет статус заявки через `ApplicationStateMachine`

Подробнее: [docs/agent-graph.md](docs/agent-graph.md)

### Конфигурация LLM

Система поддерживает три провайдера:

- **mock** — детерминированные ответы для тестирования
- **local** — Ollama с моделью `qwen2.5-abliterate:14b` (рекомендуется)
- **openai** — OpenAI-compatible API (любой провайдер)

---

## Статус модулей

| Модуль | Статус | Примечания |
|--------|--------|------------|
| FastAPI приложение | ✅ Реализован | Все роутеры, CORS, middleware |
| Аутентификация (JWT) | ✅ Реализован | Register, login, refresh |
| ORM-модели (SQLAlchemy) | ✅ Реализован | 20+ таблиц |
| State Machine (18 состояний) | ✅ Реализован | Полная карта переходов |
| Completeness Engine (18 правил) | ✅ Реализован | Строгая/мягкая валидация |
| Prompt Registry (YAML) | ✅ Реализован | Jinja2-шаблоны, версионирование |
| LLM Mock Provider | ✅ Реализован | Детерминированные ответы |
| LLM OpenAI-compatible | ✅ Реализован | Ollama, OpenAI, etc. |
| ФИПС Mock Provider | ✅ Реализован | Случайные результаты |
| NICE Classifier Agent | ✅ Реализован | Предлагает классы МКТУ |
| Absolute Grounds Agent | ✅ Реализован | ГК РФ ст.1483 п.1-4 |
| Relative Grounds Agent | ✅ Реализован | ГК РФ ст.1483 п.6 |
| Conflict Search Agents (3) | ✅ Реализован | Query builder + Analyzer + Orchestrator |
| Human Review Packager | ✅ Реализован | Пакет для юриста |
| Recommender Agent | ✅ Реализован | Итоговое мемо |
| Document Assembler Agent | ✅ Реализован | Инициирует генерацию |
| Document Generator Service | ✅ Реализован | python-docx, без шаблонов |
| RAG Pipeline (BM25) | ✅ Реализован | TF-IDF, готов к pgvector |
| Knowledge Loader | ✅ Реализован | .txt, .md файлы |
| Seed Data | ✅ Реализован | 4 пользователя, 5 клиентов, 8 заявок |
| Frontend (React) | ✅ Реализован | Dashboard, заявки, клиенты |
| Docker Compose | ✅ Реализован | API + Web + Redis |
| Alembic миграции | 🔶 Частично | Только init_db (create_all) |
| Status Monitor Agent | 🔶 Частично | Базовый polling |
| Submission Agent | 🔶 Частично | Mock submission |
| WebSocket уведомления | 🔶 Отложено | Только REST endpoint |
| Email уведомления | 🔶 Отложено | Только БД-запись |
| ФИПС SOAP API | 🔶 Отложено | Mock в MVP |
| pgvector / Qdrant | 🔶 Отложено | BM25 в MVP |
| Celery Workers | 🔶 Отложено | Inline execution в MVP |

---

## Переменные окружения

Скопируйте `.env.example` → `.env` и отредактируйте:

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./trademark.db` | URL подключения к БД |
| `SECRET_KEY` | `change-me-...` | Секрет для подписи JWT (**обязательно изменить**) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Время жизни токена (минуты) |
| `LLM_PROVIDER` | `mock` | Провайдер LLM: `mock` / `local` / `openai` |
| `LLM_MODEL` | `huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M` | Имя модели |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Base URL для Ollama / OpenAI |
| `LLM_API_KEY` | _(пусто)_ | API ключ (для OpenAI) |
| `FIPS_PROVIDER` | `mock` | Провайдер ФИПС: `mock` / `soap` |
| `VECTOR_STORE_TYPE` | `mock` | Тип хранилища: `mock` / `qdrant` / `pgvector` |
| `REDIS_URL` | `redis://localhost:6379` | URL Redis для кэша/очередей |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `CORS_ORIGINS` | `["http://localhost:3000",...]` | Разрешённые CORS origins |

---

## Документация

| Файл | Описание |
|------|----------|
| [docs/architecture.md](docs/architecture.md) | Общая архитектура системы |
| [docs/domain-model.md](docs/domain-model.md) | Доменная модель и сущности |
| [docs/state-machine.md](docs/state-machine.md) | 18 состояний заявки, карта переходов |
| [docs/agent-graph.md](docs/agent-graph.md) | Граф агентов LangGraph |
| [docs/api-contracts.md](docs/api-contracts.md) | REST API контракты |
| [docs/document-pipeline.md](docs/document-pipeline.md) | Пайплайн генерации документов |
| [docs/rag-design.md](docs/rag-design.md) | Архитектура RAG |
| [docs/prompt-registry.md](docs/prompt-registry.md) | Управление промптами |
| [docs/security.md](docs/security.md) | Безопасность и авторизация |
| [docs/testing-strategy.md](docs/testing-strategy.md) | Стратегия тестирования |

---

## Лицензия

Проприетарное программное обеспечение. Все права защищены.
