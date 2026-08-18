# Дизайн безопасности системы регистрации товарных знаков

> **Статус на 15.08.2026:** документ содержит целевые меры и не является актом
> соответствия 152-ФЗ. Фактическая модель доступа: клиент видит собственные
> данные; администратор — все заявки; юрист — созданные им и назначенные ему.
> Production-защита и инфраструктура ещё не введены в эксплуатацию.

> **Версия:** 1.0  
> **Дата:** 2026-03-29

---

## 1. Модель угроз

### 1.1 Активы для защиты

| Актив | Категория | Критичность |
|---|---|---|
| Персональные данные клиентов (ФИО, ИНН, адреса) | PII / 152-ФЗ | Критическая |
| Данные заявок на ТЗ (конфиденциальные бизнес-сведения) | Коммерческая тайна | Критическая |
| DOCX-пакеты документов | Конфиденциальные | Высокая |
| Учётные данные ФИПС API | Секреты | Критическая |
| JWT-токены пользователей | Авторизационные | Высокая |
| Промпты и методология фирмы | Интеллектуальная собственность | Средняя |

### 1.2 Модель нарушителя

| Нарушитель | Вектор | Митигация |
|---|---|---|
| Внешний злоумышленник | Эксплуатация уязвимостей API | CORS, rate limiting, WAF |
| Инсайдер (сотрудник) | Несанкционированный доступ к данным | RBAC, field-level access, аудит |
| Перехват трафика | MITM | TLS 1.3 everywhere |
| Кража токенов | XSS, session hijacking | HttpOnly cookies, CSP, CSRF |

---

## 2. RBAC — Управление доступом на основе ролей

### 2.1 Роли системы

| Роль | Описание | Пользователи |
|---|---|---|
| `admin` | Полный доступ ко всем функциям. Управление пользователями, промптами, конфигурацией | Системный администратор |
| `lawyer` | Ведение заявок: просмотр, правовая экспертиза, HITL-решения, подписание документов | Юристы фирмы |
| `manager` | Создание клиентов и заявок, мониторинг статусов, работа с клиентами | Менеджеры фирмы |
| `client` | Просмотр своих заявок, загрузка документов, ответы на запросы | Клиенты фирмы (ограниченный доступ) |

### 2.2 Матрица прав доступа к эндпоинтам

| Эндпоинт | admin | lawyer | manager | client |
|---|:---:|:---:|:---:|:---:|
| `POST /auth/login` | ✓ | ✓ | ✓ | ✓ |
| `GET /users` | ✓ | — | — | — |
| `POST /users` | ✓ | — | — | — |
| `PATCH /users/{id}` | ✓ | Свой | — | — |
| `GET /clients` | ✓ | ✓ | ✓ | Свой |
| `POST /clients` | ✓ | ✓ | ✓ | ✓ (своя карточка) |
| `GET /applications` | ✓ | ✓ | ✓ | Свои |
| `POST /applications` | ✓ | ✓ | ✓ | ✓ (своя заявка) |
| `GET /applications/{id}/fees` | ✓ | Назначенная/своя | Назначенная/своя | Своя |
| `GET /applications/{id}` | ✓ | ✓ | ✓ | Своя |
| `POST /applications/{id}/legal-review/run` | ✓ | ✓ | — | — |
| `POST /applications/{id}/legal-review/approve` | ✓ | ✓ | — | — |
| `POST /applications/{id}/classes/approve` | ✓ | ✓ | — | — |
| `POST /applications/{id}/recommendation/approve` | ✓ | ✓ | — | — |
| `POST /applications/{id}/documents/approve` | ✓ | ✓ | — | — |
| `POST /applications/{id}/submit` | ✓ | ✓ | — | — |
| `GET /audit` | ✓ | ✓ | — | — |
| `GET /admin/prompts` | ✓ | ✓(read) | — | — |
| `POST /admin/prompts` | ✓ | — | — | — |
| `PUT /admin/models/default` | ✓ | — | — | — |
| `GET /health` | ✓ | ✓ | ✓ | — |

### 2.3 Контроль доступа к данным (Data-Level Authorization)

Помимо ролевых прав, действует **владельческий контроль**:

- `client` видит карточки заявителя, созданные его аккаунтом, и заявки, созданные им либо назначенные ему.
- `manager` видит заявки, созданные им или назначенные ему.
- `lawyer` видит заявки, созданные им или назначенные ему через `assigned_lawyer_id`.
- `admin` видит всё.

Клиентская заявка не назначается всем юристам автоматически: она сразу видна
администратору, а профессиональный доступ конкретного юриста возникает после
назначения. Это предотвращает раскрытие дела посторонним сотрудникам.

```python
# backend/app/applications/api/dependencies.py
# Зависимости FastAPI для авторизации доступа к заявке

async def get_application_with_access_check(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrademarkApplicationDraft:
    """Получение заявки с проверкой прав доступа."""
    
    application = await ApplicationRepository(db).get_by_id(application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    
    # Проверка прав доступа в зависимости от роли
    if current_user.role == Role.ADMIN:
        return application  # Полный доступ
    
    if current_user.role == Role.LAWYER:
        if application.responsible_lawyer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Нет доступа к данной заявке")
    
    if current_user.role == Role.MANAGER:
        client = await ClientRepository(db).get_by_id(application.client_id)
        if client.manager_id != current_user.id:
            raise HTTPException(status_code=403, detail="Нет доступа к данной заявке")
    
    if current_user.role == Role.CLIENT:
        client = await ClientRepository(db).get_client_for_user(current_user.id)
        if application.client_id != client.id:
            raise HTTPException(status_code=403, detail="Нет доступа к данной заявке")
    
    return application
```

---

## 3. Аутентификация и управление сессиями

### 3.1 JWT-токены

| Параметр | Значение |
|---|---|
| Алгоритм | HS256 (MVP) → RS256 (Prod) |
| Access token TTL | 60 минут |
| Refresh token TTL | 30 дней |
| Хранение на клиенте | `Authorization: Bearer` в памяти (access) + HttpOnly cookie (refresh) |
| Ротация refresh token | При каждом использовании (Refresh Token Rotation) |
| Хранение в БД | Refresh tokens хранятся в таблице `refresh_tokens` с возможностью инвалидации |

### 3.2 Payload JWT

```json
{
  "sub": "uuid-пользователя",
  "email": "lawyer@firm.ru",
  "role": "lawyer",
  "iat": 1711700000,
  "exp": 1711703600,
  "jti": "uuid-токена"
}
```

### 3.3 Инвалидация токенов

- При выходе (`/auth/logout`) — refresh token удаляется из БД.
- При смене пароля — все refresh tokens пользователя инвалидируются.
- Глобальный logout (`/auth/logout-all`) — инвалидирует все активные сессии.

---

## 4. Доступ на уровне полей (Field-Level Security)

Некоторые поля скрыты в зависимости от роли:

| Поле | admin | lawyer | manager | client |
|---|:---:|:---:|:---:|:---:|
| `User.hashed_password` | — | — | — | — |
| `Client.inn` | ✓ | ✓ | ✓ | Свой |
| `AuditLog.before_state` | ✓ | ✓ | — | — |
| `LegalReview.lawyer_comment` | ✓ | ✓ | — | — |
| `LegalFinding.confidence_score` | ✓ | ✓ | — | — |
| `AgentRun.input_state` | ✓ | ✓ | — | — |
| `Submission.fips_credentials` | — | — | — | — |
| `PromptDefinition.template` | ✓ | Чтение | — | — |

Реализация через Pydantic-схемы с разными полями для разных ролей:

```python
# backend/app/applications/api/schemas.py

class ApplicationResponseBase(BaseModel):
    id: UUID
    application_number: str
    status: ApplicationStatus
    mark_type: MarkType
    working_title: str
    created_at: datetime

class ApplicationResponseLawyer(ApplicationResponseBase):
    """Расширенная версия для юриста — включает внутренние данные."""
    latest_legal_review: LegalReviewSchema | None
    agent_runs_summary: list[AgentRunSummary]
    audit_trail_url: str

class ApplicationResponseClient(ApplicationResponseBase):
    """Ограниченная версия для клиента — без внутренних данных."""
    status_description_ru: str
    next_required_action: str | None
    documents_available: list[DocumentInfo]
```

---

## 5. Маскирование PII (PII Masking)

Персональные данные маскируются в логах и ошибках:

```python
# backend/app/core/logging/pii_masker.py
# Маскирование персональных данных в структурированных логах

import re

PII_PATTERNS = {
    "inn": (r"\b(\d{10}|\d{12})\b", lambda m: m.group()[:3] + "***" + m.group()[-2:]),
    "phone": (r"\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", "***"),
    "email": (r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", lambda m: m.group().split('@')[0][:2] + "***@" + m.group().split('@')[1]),
    "passport": (r"\d{4}\s\d{6}", "****  ******"),
    "full_name": None,  # Обрабатывается отдельно через NER (если настроено)
}

class PIIMasker:
    """Маскирование PII в произвольных строках и JSON-объектах."""
    
    def mask_string(self, text: str) -> str:
        for pattern_name, pattern_data in PII_PATTERNS.items():
            if pattern_data is None:
                continue
            regex, replacement = pattern_data
            if callable(replacement):
                text = re.sub(regex, replacement, text)
            else:
                text = re.sub(regex, replacement, text)
        return text
    
    def mask_dict(self, data: dict, sensitive_keys: list[str] = None) -> dict:
        """Маскирование полей словаря по списку чувствительных ключей."""
        sensitive_keys = sensitive_keys or [
            "password", "hashed_password", "inn", "ogrn", "passport",
            "phone", "email", "legal_address", "full_name"
        ]
        ...
```

**Правила:**
- Логи уровня `INFO` и ниже — PII маскируется всегда.
- Логи уровня `ERROR` — PII маскируется, request_id сохраняется для корреляции.
- Хранилище аудита (`AuditLog`) — PII хранится в зашифрованном виде.
- LLM-промпты — PII заменяется плейсхолдерами перед отправкой: `{CLIENT_NAME}`, `{CLIENT_INN}`.

---

## 6. Защита от веб-атак

### 6.1 CSRF-защита

```python
# backend/app/core/security/csrf.py
# CSRF-защита для мутирующих операций

from fastapi import Request, HTTPException

class CSRFProtection:
    """Double Submit Cookie паттерн для CSRF-защиты."""
    
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    
    async def __call__(self, request: Request):
        if request.method in self.SAFE_METHODS:
            return
        
        # Валидация CSRF-токена из заголовка
        csrf_header = request.headers.get("X-CSRF-Token")
        csrf_cookie = request.cookies.get("csrf_token")
        
        if not csrf_header or not csrf_cookie:
            raise HTTPException(status_code=403, detail="CSRF token missing")
        
        if not secrets.compare_digest(csrf_header, csrf_cookie):
            raise HTTPException(status_code=403, detail="CSRF token invalid")
```

### 6.2 XSS-защита

Заголовки безопасности, устанавливаемые Nginx:

```nginx
# nginx/conf.d/security_headers.conf
# Заголовки безопасности для всех ответов

add_header Content-Security-Policy 
    "default-src 'self'; 
     script-src 'self' 'nonce-{NONCE}'; 
     style-src 'self' 'unsafe-inline'; 
     img-src 'self' data:; 
     connect-src 'self' wss://; 
     frame-ancestors 'none';" always;

add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

### 6.3 Rate Limiting

```python
# backend/app/core/middleware/rate_limiter.py
# Ограничение скорости запросов по эндпоинту и пользователю

RATE_LIMITS = {
    "POST /auth/login":              RateLimit(requests=10,  window_seconds=60),   # Антибрут
    "POST /auth/refresh":            RateLimit(requests=30,  window_seconds=60),
    "POST /applications/*/validate": RateLimit(requests=5,   window_seconds=300),  # Ресурсоёмко
    "POST /applications/*/legal-review/run": RateLimit(requests=3, window_seconds=300),
    "POST /applications/*/conflicts/search": RateLimit(requests=3, window_seconds=300),
    "default":                       RateLimit(requests=100, window_seconds=60),
}
```

### 6.4 Валидация входных данных

- Все входные данные проходят через **Pydantic v2** с `model_config = ConfigDict(strict=True)`.
- Поля типа `string` имеют максимальную длину (`max_length`).
- UUID-параметры пути валидируются как UUID (защита от SQL injection через параметры).
- Загружаемые файлы: проверка MIME-типа по содержимому (не только расширению), ограничение 20 МБ.

---

## 7. Шифрование данных

### 7.1 В транзите (In-Transit)

- TLS 1.3 на всех публичных эндпоинтах (Nginx termination).
- Внутренняя сеть (контейнеры): mTLS планируется на стадии Post-MVP.

### 7.2 В покое (At-Rest)

| Данные | Метод шифрования |
|---|---|
| PostgreSQL | Шифрование диска (LUKS) на уровне ОС |
| Файлы документов (MinIO) | Server-Side Encryption (SSE-S3) |
| Секреты (ФИПС credentials, API keys) | HashiCorp Vault / переменные среды `.env` с restrictive permissions |
| Refresh tokens в БД | Хранятся как `sha256(token)`, не в открытом виде |

---

## 8. Журнал аудита (Audit Logging)

### 8.1 Что журналируется

| Категория | Примеры событий |
|---|---|
| Аутентификация | Вход, выход, неудачные попытки входа, смена пароля |
| Заявки | Создание, каждый переход статуса, изменение данных |
| HITL-решения | Каждое решение юриста с комментарием |
| Документы | Создание, одобрение, отклонение пакета |
| Агенты | Запуск, завершение, ошибки |
| Подача | Отправка в ФИПС, получение квитанции |
| Пользователи | Создание, деактивация, смена роли |
| Промпты | Создание, обновление, активация версии |
| Конфигурация | Смена модели LLM, параметров системы |

### 8.2 Структура записи аудита

```python
class AuditLogEntry(BaseModel):
    id: UUID
    user_id: UUID | None          # None для системных событий
    session_id: str | None
    entity_type: EntityType
    entity_id: UUID
    action: str                   # Глагол в past tense, напр.: "status_changed"
    before_state: dict | None     # Состояние до (PII зашифрован)
    after_state: dict | None      # Состояние после (PII зашифрован)
    ip_address: str               # IPv4/IPv6 клиента
    user_agent: str
    request_id: str               # Для корреляции с HTTP-логами
    created_at: datetime          # UTC
```

### 8.3 Политика хранения

- Записи не обновляются и не удаляются (append-only).
- Хранение: 5 лет (требование 152-ФЗ для персональных данных).
- Доступ: только `admin` и `lawyer` (read-only через API).
- Экспорт: CSV/JSON по запросу admin.

---

## 9. Защита секретов

```python
# backend/app/core/config.py
# Конфигурация с явным разделением публичных и секретных настроек

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Публичные настройки
    APP_NAME: str = "Trademark Registration System"
    DEBUG: bool = False
    
    # Секреты — ТОЛЬКО через переменные среды или Vault
    SECRET_KEY: str                # JWT подписание
    DATABASE_URL: str              # Строка подключения к БД
    FIPS_API_KEY: str | None = None  # Ключ ФИПС API (None для mock)
    SMTP_PASSWORD: str | None = None
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Секреты никогда не попадают в логи
        secrets_dir="/run/secrets",  # Docker secrets
    )
    
    def __repr__(self) -> str:
        # Исключаем секреты из repr
        return f"Settings(APP_NAME={self.APP_NAME}, DEBUG={self.DEBUG})"
```

**Правила:**
- Секреты не хранятся в системе контроля версий (`.env` в `.gitignore`).
- CI/CD использует секреты из GitHub Secrets / Vault.
- Периодическая ротация (SECRET_KEY — каждые 90 дней, FIPS_API_KEY — при смене).

---

## 10. Политика паролей

| Параметр | Значение |
|---|---|
| Минимальная длина | 12 символов |
| Требования | Буквы верхнего и нижнего регистра + цифры + спецсимволы |
| Хэширование | bcrypt, cost factor 12 |
| Блокировка | 5 неудачных попыток → блокировка на 30 минут |
| Принудительная смена | При первом входе (временный пароль) |
| История паролей | Последние 10 паролей не повторяются |
