# Контракты API системы регистрации товарных знаков

> **Статус документа:** историческая проектная спецификация. В ней есть как
> реализованные, так и отсутствующие маршруты; поддерживать вручную полный
> дубликат OpenAPI больше не планируется. Фактическая схема доступна на `/docs`,
> общий срез — в [`current-state.md`](current-state.md).

> **Версия:** 1.0  
> **Дата:** 2026-03-29  
> **Base URL:** `/api/v1`  
> **Формат:** JSON  
> **Аутентификация:** Bearer JWT (за исключением `/auth/login`, `/health`)

---

## 1. Общие соглашения

### 1.1 Формат ответов

Все ответы оборачиваются в конверт:

```json
// Успешный ответ
{
  "success": true,
  "data": { ... },
  "meta": {
    "request_id": "uuid",
    "timestamp": "2026-03-29T12:00:00Z"
  }
}

// Ответ со списком (с пагинацией)
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "request_id": "uuid",
    "timestamp": "2026-03-29T12:00:00Z",
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 150,
      "total_pages": 8
    }
  }
}

// Ошибка
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Ошибка валидации входных данных",
    "details": [ { "field": "inn", "message": "ИНН должен содержать 10 или 12 цифр" } ]
  },
  "meta": { "request_id": "uuid", "timestamp": "..." }
}
```

### 1.2 HTTP-коды статусов

| Код | Значение |
|---|---|
| 200 | Успешный запрос |
| 201 | Создан новый ресурс |
| 202 | Запрос принят, обрабатывается асинхронно |
| 400 | Ошибка валидации |
| 401 | Не аутентифицирован |
| 403 | Недостаточно прав |
| 404 | Ресурс не найден |
| 409 | Конфликт (дублирующийся ресурс) |
| 422 | Бизнес-логика отклонила операцию |
| 429 | Превышен лимит запросов |
| 500 | Внутренняя ошибка сервера |

### 1.3 Пагинация

Все list-эндпоинты принимают `?page=1&page_size=20`.

### 1.4 Заголовки запроса

```
Authorization: Bearer <access_token>
Content-Type: application/json
Accept-Language: ru
X-Request-ID: <uuid>  (опц., если не передан — генерируется сервером)
```

---

## 2. Аутентификация `/auth`

### POST `/auth/login`

Получение JWT-токена по логину и паролю.

**Запрос:**
```json
{
  "email": "lawyer@firm.ru",
  "password": "s3cur3P@ssw0rd"
}
```

**Ответ 200:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 3600,
    "user": {
      "id": "uuid",
      "email": "lawyer@firm.ru",
      "full_name": "Иванов Иван Иванович",
      "role": "lawyer"
    }
  }
}
```

**Ошибки:** 401 — неверные учётные данные; 403 — аккаунт деактивирован.

---

### POST `/auth/refresh`

Обновление access-токена через refresh-токен.

**Запрос:**
```json
{ "refresh_token": "eyJ..." }
```

**Ответ 200:** Аналогично `/auth/login`, без `user`.

---

### POST `/auth/logout`

Инвалидация refresh-токена.

**Запрос:** Тело пустое. Использует токен из `Authorization` заголовка.  
**Ответ 200:** `{ "success": true, "data": { "message": "Сессия завершена" } }`

---

### GET `/auth/me`

Получение профиля текущего пользователя.

**Ответ 200:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "email": "lawyer@firm.ru",
    "full_name": "Иванов Иван Иванович",
    "role": "lawyer",
    "is_active": true,
    "created_at": "2026-01-15T10:00:00Z"
  }
}
```

---

## 3. Пользователи `/users`

**Доступ:** admin

### GET `/users`

Список пользователей системы.

**Query params:** `?role=lawyer&is_active=true&page=1&page_size=20`

**Ответ 200:** Список `UserResponse`.

---

### POST `/users`

Создание нового пользователя.

**Запрос:**
```json
{
  "email": "new.lawyer@firm.ru",
  "password": "TempP@ss123",
  "full_name": "Петрова Анна Сергеевна",
  "role": "lawyer"
}
```

**Ответ 201:** `UserResponse`.

---

### GET `/users/{user_id}`
### PATCH `/users/{user_id}`
### DELETE `/users/{user_id}` — soft delete (`is_active = false`)

---

## 4. Клиенты `/clients`

**Доступ:** admin, lawyer, manager

### GET `/clients`

**Query params:** `?search=ООО&client_type=legal_entity&manager_id=uuid`

**Ответ 200:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "client_type": "legal_entity",
      "short_name": "ООО «Рога и Копыта»",
      "full_legal_name": "Общество с ограниченной ответственностью «Рога и Копыта»",
      "inn": "7712345678",
      "ogrn": "1027739000000",
      "email": "info@rogaikopyta.ru",
      "phone": "+7 (495) 123-45-67",
      "manager_id": "uuid",
      "is_active": true,
      "created_at": "2026-02-01T09:00:00Z"
    }
  ]
}
```

---

### POST `/clients`

**Запрос:**
```json
{
  "client_type": "legal_entity",
  "short_name": "ООО «Примерная»",
  "full_legal_name": "Общество с ограниченной ответственностью «Примерная»",
  "inn": "7712345679",
  "ogrn": "1027739000001",
  "legal_address": "125009, г. Москва, ул. Тверская, д. 1",
  "postal_address": "125009, г. Москва, ул. Тверская, д. 1",
  "email": "info@primernaya.ru",
  "phone": "+7 (495) 987-65-43",
  "manager_id": "uuid"
}
```

**Ответ 201:** `ClientResponse` (полный объект клиента).

---

### GET `/clients/{client_id}`
### PATCH `/clients/{client_id}`

Частичное обновление. Изменения записываются в `AuditLog`.

---

### GET `/clients/{client_id}/representatives`

### POST `/clients/{client_id}/representatives`

### PUT `/clients/{client_id}/representatives/{representative_id}`

Создание и полная правка представителя. Доступ проверяется по владельцу карточки
заявителя; реквизиты представителя не записываются в открытый аудит.

```json
{
  "full_name": "Сидоров Пётр Алексеевич",
  "role": "Патентный поверенный",
  "address": "125009, Москва, ул. Тверская, д. 1",
  "email": "sidorov@primernaya.ru",
  "phone": "+7 (926) 111-22-33",
  "is_patent_attorney": true,
  "patent_attorney_registration_number": "1234",
  "authority_type": "power_of_attorney",
  "poa_reference": "№ 15 от 28.08.2026"
}
```

`authority_type`: `power_of_attorney`, `law` или `charter`.

---

## 5. Заявки `/applications`

**Доступ:** admin, lawyer, manager (создание); client (просмотр своих)

### GET `/applications`

**Query params:** `?client_id=uuid&status=legal_precheck_running&lawyer_id=uuid&from_date=2026-01-01`

**Ответ 200:** Список `ApplicationListItem` (краткая форма).

```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "application_number": "TZ-2026-00042",
      "client": { "id": "uuid", "short_name": "ООО «Примерная»" },
      "working_title": "ПРИМЕРНАЯ — словесный ТЗ",
      "mark_type": "word",
      "status": "legal_precheck_running",
      "responsible_lawyer": { "id": "uuid", "full_name": "Иванов И.И." },
      "created_at": "2026-03-01T10:00:00Z",
      "updated_at": "2026-03-29T08:00:00Z"
    }
  ]
}
```

---

### POST `/applications`

Создание новой заявки.

**Запрос:**
```json
{
  "client_id": "uuid",
  "responsible_lawyer_id": "uuid",
  "mark_type": "word",
  "working_title": "ПРИМЕРНАЯ — словесный ТЗ",
  "mark": {
    "verbal_element": "ПРИМЕРНАЯ",
    "description": null,
    "color_claim": null,
    "transliteration": "PRIMERNAYA"
  },
  "preliminary_goods_services": [
    "Программное обеспечение",
    "Консультационные услуги в области информационных технологий"
  ],
  "representative_id": 42
}
```

`representative_id` должен принадлежать заявителю этой заявки. Значение `null`
означает самостоятельную подачу и удаляет ранее выбранного представителя.

**Ответ 201:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "application_number": "TZ-2026-00043",
    "status": "draft",
    ...
  }
}
```

---

### GET `/applications/{id}`

Полный объект заявки со всеми вложенными данными.

```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "application_number": "TZ-2026-00043",
    "status": "recommendation_ready",
    "mark_type": "word",
    "mark": { ... },
    "client": { ... },
    "responsible_lawyer": { ... },
    "goods_services": [ ... ],
    "approved_nice_classes": [9, 42],
    "latest_legal_review": { ... },
    "latest_recommendation": { ... },
    "document_package": { ... },
    "submission": null,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

---

### POST `/applications/{id}/validate`

Запуск агента `IntakeValidator`.

**Запрос:** `{}` (пустое тело)

**Ответ 202:**
```json
{
  "success": true,
  "data": {
    "agent_run_id": "uuid",
    "status": "running",
    "message": "Валидация запущена. Подпишитесь на WebSocket для получения результатов."
  }
}
```

---

### POST `/applications/{id}/request-missing-info`

Отправка клиенту запроса на предоставление недостающих данных.

**Запрос:**
```json
{
  "missing_fields": [
    { "field_path": "mark.image_file_path", "description_ru": "Необходим файл изображения обозначения", "is_blocking": true }
  ],
  "custom_message_ru": "Просим дополнить заявку в срок до 15.04.2026."
}
```

**Ответ 200:** `{ "notification_id": "uuid", "status": "awaiting_client_data" }`

---

### POST `/applications/{id}/legal-review/run`

Запуск правовой экспертизы (AbsoluteGrounds + RelativeGrounds).

**Запрос:**
```json
{
  "review_type": "full",
  "rag_context_limit": 10
}
```

**Ответ 202:** `{ "agent_run_id": "uuid", "status": "running" }`

---

### GET `/applications/{id}/legal-review`

Получение результатов правовой экспертизы.

**Ответ 200:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "review_type": "full",
    "status": "awaiting_lawyer_approval",
    "overall_risk": "medium",
    "summary_ru": "Обозначение в целом регистрируемо. Выявлены риски по п.2 ст.1483 ГК РФ.",
    "findings": [
      {
        "id": "uuid",
        "finding_type": "absolute_ground",
        "severity": "warning",
        "article_reference": "ст. 1483, п. 2 ГК РФ",
        "description_ru": "Обозначение содержит описательный элемент «ПРИМЕРНАЯ»...",
        "recommendation_ru": "Рекомендуется добавить оригинальный графический элемент.",
        "confidence_score": 0.82,
        "rag_citations": [
          { "source_code": "gk_rf_part4", "chunk_id": "uuid", "article": "ст. 1483", "excerpt": "..." }
        ]
      }
    ],
    "lawyer_approved_at": null,
    "agent_run_id": "uuid"
  }
}
```

---

### POST `/applications/{id}/legal-review/approve`

HITL Checkpoint 1: юрист одобряет результаты экспертизы.

**Доступ:** lawyer

**Запрос:**
```json
{
  "decision": "approved",
  "comment": "Согласен с выводами. Пункт о описательности — предупреждение, не блокирует."
}
```

**Ответ 200:** Обновлённый `LegalReview`. Статус заявки → `classes_review`.

---

### POST `/applications/{id}/classes/suggest`

Запуск агента `NiceClassification`.

**Запрос:**
```json
{
  "business_description": "Разработка мобильных приложений для финансового сектора"
}
```

**Ответ 202:** `{ "agent_run_id": "uuid" }`

---

### GET `/applications/{id}/classes/suggestions`

**Ответ 200:** Список `NiceClassSuggestion`.

---

### POST `/applications/{id}/classes/approve`

HITL Checkpoint 2: юрист утверждает классы МКТУ.

**Запрос:**
```json
{
  "approved_classes": [9, 35, 42],
  "modifications": [
    { "nice_class": 9, "items_to_add": ["Мобильные приложения"], "items_to_remove": [] }
  ],
  "comment": "Добавил класс 35 для дистрибуции ПО."
}
```

**Ответ 200:** `{ "status": "conflict_search_running", "approved_classes": [9, 35, 42] }`

---

### POST `/applications/{id}/conflicts/search`

Запуск поиска конфликтующих обозначений.

**Запрос:**
```json
{
  "search_strategy": "comprehensive",
  "custom_queries": []
}
```

**Ответ 202:** `{ "job_id": "uuid", "agent_run_id": "uuid" }`

---

### GET `/applications/{id}/conflicts`

**Ответ 200:**
```json
{
  "success": true,
  "data": {
    "job_id": "uuid",
    "status": "completed",
    "overall_conflict_risk": "medium",
    "results": [
      {
        "id": "uuid",
        "fips_trademark_number": "0123456",
        "fips_trademark_title": "ПРИМЕРНАЯ КОМПАНИЯ",
        "owner_name": "ООО «Другая Компания»",
        "nice_classes": [42],
        "similarity_type": "semantic",
        "similarity_score": 0.71,
        "risk_level": "medium",
        "analysis_notes_ru": "Семантическое сходство в части слова «ПРИМЕРНАЯ»...",
        "status": "active",
        "registration_date": "2021-05-12",
        "expiry_date": "2031-05-12"
      }
    ]
  }
}
```

---

### POST `/applications/{id}/recommendation`

Запуск агента `Recommendation` (синтез итоговой рекомендации).

**Запрос:** `{}`  
**Ответ 202:** `{ "agent_run_id": "uuid" }`

---

### GET `/applications/{id}/recommendation`

**Ответ 200:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "recommendation": "proceed_with_modifications",
    "executive_summary_ru": "Регистрация обозначения возможна при условии...",
    "legal_analysis_ru": "По результатам экспертизы выявлен средний уровень рисков...",
    "risk_assessment_ru": "Основной риск — сходство с ТЗ №0123456...",
    "proposed_actions": [
      { "action": "Дополнить заявку дискламацией словесного элемента «ПРИМЕРНАЯ»", "priority": "high" }
    ],
    "overall_confidence": 0.78,
    "status": "awaiting_approval"
  }
}
```

---

### POST `/applications/{id}/recommendation/approve`

HITL Checkpoint 3.

**Запрос:**
```json
{
  "decision": "approved",
  "comment": "Принято к исполнению. Дискламация согласована с клиентом."
}
```

---

### POST `/applications/{id}/documents/generate`

Запуск агента `DocumentAssembly`.

**Запрос:** `{}`  
**Ответ 202:** `{ "agent_run_id": "uuid" }`

---

### GET `/applications/{id}/documents`

**Ответ 200:**
```json
{
  "success": true,
  "data": {
    "package_id": "uuid",
    "package_version": "1.0",
    "status": "assembled",
    "documents": [
      {
        "template_code": "trademark_application_form",
        "file_name": "Заявление_на_регистрацию_ТЗ_TZ-2026-00043.docx",
        "file_path": "/documents/uuid/...",
        "download_url": "/api/v1/documents/uuid/download",
        "version": "2.1",
        "checksum": "sha256:abc..."
      }
    ],
    "completeness_check": { "is_complete": true, "missing_docs": [] }
  }
}
```

---

### POST `/applications/{id}/documents/approve`

HITL Checkpoint 4.

**Запрос:**
```json
{
  "decision": "approved",
  "comment": "Документы проверены, подпись ЭП поставлена."
}
```

**Ответ 200:** `{ "status": "ready_for_submission" }`

---

### POST `/applications/{id}/submit`

Подача в ФИПС. Требует `status = ready_for_submission`.

**Запрос:**
```json
{
  "submission_channel": "fips_api",
  "confirm": true
}
```

**Ответ 202:**
```json
{
  "success": true,
  "data": {
    "submission_id": "uuid",
    "status": "in_progress",
    "message": "Документы переданы на подачу в ФИПС"
  }
}
```

---

### GET `/applications/{id}/status`

Текущий статус заявки и история событий.

**Ответ 200:**
```json
{
  "success": true,
  "data": {
    "application_id": "uuid",
    "current_status": "status_monitoring",
    "fips_receipt_number": "2026123456",
    "status_events": [
      {
        "event_type": "status_change",
        "previous_status": "submitted",
        "new_status": "status_monitoring",
        "description_ru": "Заявка принята к рассмотрению ФИПС",
        "event_date": "2026-03-29T10:00:00Z",
        "requires_client_action": false
      }
    ],
    "next_action": null,
    "next_action_deadline": null
  }
}
```

---

### GET `/applications/{id}/history`

Полная история всех агентных запусков и изменений статусов.

---

## 6. Уведомления `/notifications`

### GET `/notifications`

**Query params:** `?status=pending&channel=email&page=1`

### GET `/notifications/{id}`
### POST `/notifications/{id}/mark-read`
### POST `/notifications/mark-all-read`

### GET `/notifications/preferences`
### PUT `/notifications/preferences`

```json
{
  "email_enabled": true,
  "telegram_enabled": false,
  "telegram_chat_id": null,
  "notify_on": ["status_change", "action_required", "document_ready"]
}
```

---

## 7. Вебхуки `/webhooks`

### POST `/webhooks/fips`

Входящий вебхук от ФИПС (статусные обновления).

**Запрос (от ФИПС):**
```json
{
  "request_id": "2026123456",
  "event_type": "STATUS_CHANGE",
  "new_status": "EXAMINATION_STARTED",
  "event_date": "2026-03-29T10:00:00Z"
}
```

**Ответ 200:** `{ "received": true }`

**Безопасность:** Валидация HMAC-подписи из заголовка `X-FIPS-Signature`.

---

## 8. Административные эндпоинты `/admin`

### Управление промптами `/admin/prompts`

#### GET `/admin/prompts`

Список всех промптов реестра.

#### GET `/admin/prompts/{code}`

Получение промпта по коду с историей версий.

#### POST `/admin/prompts`

Создание нового промпта.

**Запрос:**
```json
{
  "prompt_code": "absolute_grounds_check",
  "name_ru": "Проверка абсолютных оснований",
  "template": "Ты — юридический ИИ-ассистент...\n\nКонтекст из базы знаний:\n{rag_context}\n\nДанные обозначения:\n{mark_data}\n\n...",
  "input_variables": { "rag_context": "str", "mark_data": "dict" },
  "output_schema": { "$schema": "http://json-schema.org/draft-07/schema", "type": "object", "properties": { "findings": { "type": "array" } } },
  "temperature": 0.1,
  "max_tokens": 4096
}
```

#### PUT `/admin/prompts/{code}`

Обновление промпта (создаёт новую версию, старая сохраняется).

#### POST `/admin/prompts/{code}/activate`

Активация версии промпта.

#### GET `/admin/prompts/{code}/versions`

История всех версий промпта.

---

### Управление моделями `/admin/models`

#### GET `/admin/models`

Список доступных LLM-провайдеров и моделей.

**Ответ 200:**
```json
{
  "success": true,
  "data": {
    "current_default": "huihui_ai/qwen2.5-abliterate:14b",
    "provider": "ollama",
    "available_models": [
      { "model_id": "huihui_ai/qwen2.5-abliterate:14b", "is_default": true, "context_window": 32768 },
      { "model_id": "qwen2.5:7b", "is_default": false, "context_window": 32768 }
    ]
  }
}
```

#### PUT `/admin/models/default`

Смена модели по умолчанию.

```json
{ "model_id": "qwen2.5:7b", "provider": "ollama" }
```

---

### Управление заданиями `/admin/jobs`

#### GET `/admin/jobs`

**Query params:** `?status=running&job_type=status_poll`

#### GET `/admin/jobs/{id}`
#### POST `/admin/jobs/{id}/cancel`
#### POST `/admin/jobs/{id}/retry`

#### GET `/admin/jobs/scheduled`

Список запланированных задач APScheduler.

---

## 9. Аудит `/audit`

**Доступ:** admin, lawyer

### GET `/audit`

**Query params:** `?entity_type=application&entity_id=uuid&user_id=uuid&from=2026-01-01&to=2026-03-31`

**Ответ 200:**
```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "user": { "id": "uuid", "full_name": "Иванов И.И.", "role": "lawyer" },
      "entity_type": "application",
      "entity_id": "uuid",
      "action": "status_changed",
      "before_state": { "status": "intake_review" },
      "after_state": { "status": "legal_precheck_running" },
      "ip_address": "10.0.0.5",
      "request_id": "uuid",
      "created_at": "2026-03-29T08:00:00Z"
    }
  ]
}
```

### GET `/audit/{id}`

Полная запись аудита с полными состояниями до/после.

---

## 10. Сервисные эндпоинты

### GET `/health`

**Ответ 200:**
```json
{
  "status": "healthy",
  "version": "1.2.0",
  "build": "2026-03-29-abc123",
  "checks": {
    "database": "ok",
    "vector_store": "ok",
    "llm_provider": "ok",
    "fips_provider": "degraded",
    "storage": "ok"
  },
  "uptime_seconds": 86400
}
```

### GET `/health/ready`

Проверка готовности (liveness probe для K8s).

### GET `/metrics`

Prometheus-метрики в text/plain формате.

```
# HELP http_requests_total Суммарное количество HTTP-запросов
# TYPE http_requests_total counter
http_requests_total{method="POST",endpoint="/applications",status="201"} 42

# HELP agent_run_duration_seconds Время выполнения агентов
# TYPE agent_run_duration_seconds histogram
agent_run_duration_seconds_bucket{agent="absolute_grounds",le="5.0"} 38
...
```

---

## 11. Загрузка файлов

### POST `/documents/{document_id}/upload`

Загрузка файла документа (multipart/form-data).

**Content-Type:** `multipart/form-data`  
**Поля:** `file` (binary), `description` (string, опц.)  
**Ограничения:** max 20 MB; форматы: DOCX, PDF, PNG, JPG, SVG.

### GET `/documents/{document_id}/download`

Скачивание файла документа.

**Ответ:** Binary stream с заголовками `Content-Disposition`, `Content-Type`.

---

## 12. WebSocket API

### WS `/ws/applications/{id}`

Подписка на события по заявке в реальном времени.

**Формат сообщений сервера:**
```json
{
  "event": "agent_progress",
  "data": {
    "agent_run_id": "uuid",
    "agent_name": "absolute_grounds",
    "status": "running",
    "progress_message_ru": "Анализирую абсолютные основания отказа...",
    "completed_steps": 3,
    "total_steps": 7
  },
  "timestamp": "2026-03-29T12:00:00Z"
}
```

**Типы событий:**
- `agent_progress` — прогресс выполнения агента
- `agent_completed` — агент завершил работу
- `agent_failed` — ошибка агента
- `status_changed` — изменение статуса заявки
- `hitl_required` — требуется действие юриста
- `notification` — новое уведомление

---

## 13. Коды ошибок бизнес-логики

| Код | Описание |
|---|---|
| `APPLICATION_WRONG_STATUS` | Операция недопустима в текущем статусе заявки |
| `HITL_REQUIRED` | Требуется действие юриста перед продолжением |
| `AGENT_ALREADY_RUNNING` | Агент уже запущен для данной заявки |
| `DOCUMENT_PACKAGE_INCOMPLETE` | Пакет документов неполный |
| `FIPS_UNAVAILABLE` | ФИПС API временно недоступен |
| `LLM_PROVIDER_ERROR` | Ошибка LLM-провайдера |
| `INN_DUPLICATE` | Клиент с таким ИНН уже существует |
| `PROMPT_NOT_FOUND` | Промпт с указанным кодом не найден |
| `INSUFFICIENT_RAG_COVERAGE` | Недостаточно источников в базе знаний |

---

## 14. Реестр товарных знаков (read-only)

Все методы требуют Bearer-токен. Поиск и просмотр карточки доступны ролям
`admin`, `lawyer`, `manager`; список наборов официального API — только
`admin` и `lawyer`.

### POST `/api/v1/registry/search`

Ищет зарегистрированные товарные знаки, опубликованные заявки либо обе
коллекции. При `source: "both"` результаты чередуются, чтобы небольшой лимит
не был целиком занят первой коллекцией.

```json
{
  "query": "Регистр",
  "classes": [9, 42],
  "search_type": "fuzzy",
  "source": "both",
  "max_results": 20
}
```

`search_type`: `exact`, `fuzzy`, `phonetic`, `transliteration`, `semantic`.
`source`: `registrations`, `applications`, `both`. Максимальный допустимый
`max_results` — 200.

```json
{
  "provider": "rospatent_public",
  "source": "both",
  "total": 2,
  "records": [
    {
      "record_id": "registration:123456",
      "external_id": "123456",
      "source": "registration",
      "mark_text": "РЕГИСТР",
      "mark_type": "word",
      "owner": "Правообладатель",
      "classes": [9, 42],
      "status": "registered",
      "filing_date": "2024-01-15",
      "registration_date": "2025-02-10",
      "application_number": "2024700000",
      "registration_number": "123456",
      "image_url": null
    }
  ]
}
```

### GET `/api/v1/registry/records/{record_id}`

Возвращает нормализованную карточку по идентификатору из поиска. Для
публичного провайдера полнота карточки зависит от данных поисковой платформы.

### GET `/api/v1/registry/datasets`

Возвращает доступные наборы официального Open API. В публичном и mock-режимах
список может быть пустым.

### Участие реестра в полном анализе

Отдельный вызов API реестра ничего не записывает и не запускает LLM. При
запуске полного анализа система сначала ищет регистрации и заявки в классах,
ранее выбранных в деле, затем делает ограниченный широкий контроль,
рассчитывает оценки сходства и до порогового отсечения передаёт модели до 10
верхних записей. Результат аудируется
в `RiskAssessment.verification_json`:

- `class_first_search`, `selected_class_records`, `broader_control_records` —
  порядок и охват двух фаз поиска;
- `llm_registry_records_sent` — число записей, переданных модели;
- `llm_elevated_record_ids` — допороговые карточки, которые модель обоснованно
  подняла на ручную проверку;
- `llm_registry_review` — резюме, общее наблюдение, уверенность модели и
  комментарии, привязанные к существующим `record_id`;
- `verification_method` включает `llm_registry_review`, только если модель
  успешно вернула корректный структурированный ответ.

Модель не изменяет детерминированные оценки сходства. Ошибка LLM не делает
реестровый поиск неуспешным. Если значимые карточки не выявлены, относительный
анализ возвращает `is_inconclusive: true`, а не утверждение о низком риске.

## Фоновый анализ и подтверждение клиентских данных

### POST `/api/v1/applications/{application_id}/full-analysis/jobs`

Создаёт фоновое задание полного анализа и возвращает `202 Accepted`. Повторный
запрос не создаёт дубль, пока по заявке уже есть активное задание. Необязательное
тело:

```json
{"retry_incomplete_only": true}
```

Поля ответа включают `id`, `status`, `progress`, `current_step`, `message`,
`retry_count`, `max_retries`, `error_message`, `created_at`, `started_at` и
`completed_at`. Статусы активного задания: `queued`, `running`, `retrying`;
терминальные статусы: `completed`, `failed`, `cancelled`.

Клиент может запускать анализ только своей заявки. Администратор, назначенный
юрист или менеджер должны одновременно иметь право запуска и доступ к делу.

### GET `/api/v1/applications/{application_id}/full-analysis/jobs/latest`

Возвращает последнее фоновое задание заявки. Если заданий ещё нет, отвечает
`404`. Клиентский интерфейс опрашивает endpoint только пока статус активный,
показывает сохранённый прогресс и после терминального статуса автоматически
загружает итоговый отчёт.

Задание арендуется worker-ом атомарно на уровне БД. Heartbeat продлевает аренду,
просроченное задание доступно другому процессу, а уникальный token попытки не
даёт запоздавшему worker-у сохранить результат. Повторный HTTP-запрос также
защищён уникальным активным ключом заявки. Локально worker встроен в API;
production запускает отдельный процесс с тем же HTTP-контрактом.

### GET `/api/v1/applications/{application_id}/data-confirmation`

Возвращает `confirmed` и идентификатор последнего действующего подтверждения.
Подтверждение считается недействительным, если после него менялась заявка,
связанная карточка заявителя или решение по классу МКТУ.

### POST `/api/v1/applications/{application_id}/data-confirmation`

Создаёт аудируемое подтверждение текущих данных (`201 Created`). Наличие этого
подтверждения проверяется сервером при расчёте готовности финального ZIP; одного
frontend-флага недостаточно.

Синхронный `POST /api/v1/risk/applications/{application_id}/full-analysis`
сохранён для совместимости профессионального интерфейса. В новом клиентском
пути используется фоновый endpoint.

## Клиентский черновик и пошлины

### Ответ на уведомление Роспатента

`GET/POST /api/v1/applications/{application_id}/office-actions` возвращает
историю или создаёт отдельный проект ответа. `PUT
/api/v1/applications/{application_id}/office-actions/{response_id}` сохраняет
срок, факты об однородности, доказательства различительной способности и ссылки
на загруженные документы. Подтверждённый пункт обязан содержать конкретный факт;
все `document_ids` должны принадлежать тому же делу.

`POST .../{response_id}/generate` передаёт LLM текст уведомления и только
подтверждённые непустые факты. Ответ содержит `notice_summary`,
`response_summary`, `missing_evidence`, `draft_text` и статус `generated`.
`GET .../{response_id}/download` отдаёт редактируемый DOCX и возвращает `409`,
пока черновик не сформирован. Подробные гарантии описаны в
[`office-action-responses.md`](office-action-responses.md).

### Видимость клиентской заявки

Клиентский интерфейс вызывает `POST /api/v1/applications` для карточки заявителя,
которую до этого создал тот же аккаунт. После создания:

- клиент продолжает видеть собственное дело;
- администратор получает его в общем `GET /api/v1/applications` без отдельной
  операции передачи;
- юрист не видит дело до заполнения `assigned_lawyer_id` администратором;
- после назначения юрист получает доступ к карточке и расчёту пошлин.

До production endpoint должен дополнительно проверять принадлежность переданного
`client_id` текущему клиентскому аккаунту. Сейчас принадлежность заявки после
создания определяется `created_by_user_id`, а корректную пару заявитель–заявка
обеспечивает клиентский маршрут.

### GET `/api/v1/applications/{application_id}/draft-preview/download`

Скачивает текущий предзаполненный бланк в DOCX как неутверждённый рабочий
черновик. Доступ разрешён только владельцу дела, назначенному сотруднику или
администратору. Это не заменяет защищённую выгрузку утверждённой версии через
`/api/v1/drafts/{draft_id}/download`.

### GET `/api/v1/applications/{application_id}/fees`

Возвращает расчёт обязательных платежей по выбранным классам: формальную
экспертизу (2.1), экспертизу обозначения (2.4), регистрацию и электронное
свидетельство (2.11), а также необязательную доплату за бумажное свидетельство
(2.14). Ответ содержит основание выбора классов, дату и версию правил,
официальную ссылку и предупреждения о факторах, не включённых в сумму.

### GET `/api/v1/applications/{application_id}/filing-package`

Возвращает готовность ZIP-пакета для самостоятельной подачи. Ответ содержит
`ready`, понятные блокирующие пункты с целевым разделом (`data`/`check`),
манифест документов, подтверждённые классы, общий риск и суммы двух этапов.
Поле `requirements` содержит версионированный manifest применимости полей и
приложений: тип правила, `applicable`, `required` и `satisfied`. Тот же manifest
используют экран проверки, Completeness Engine, проверка ZIP и генератор DOCX;
поэтому физлицу не предлагается ОГРН, а ИП получает подпись ОГРНИП.
Поле `field_sources` содержит версию и список источников значений. Элемент
включает `code`, `source` (`document`, `user`, `system`, `rospatent`), понятные
`label` и `detail`, признаки `filled` и `verification_required`. Источник
определяется сравнением текущего значения с извлечёнными полями и сохранёнными
автоматическими предложениями, а не по одному факту заполненности.
Служебные ORM-объекты и содержимое документов в JSON не возвращаются.
Среди блокирующих пунктов может быть `data_confirmation`: после изменения
реквизитов пользователь должен повторно подтвердить проверку данных.

### GET `/api/v1/applications/{application_id}/filing-package/download`

Формирует ZIP только при `ready=true`. Архив разделён на `01_ДЛЯ_ПОДАЧИ` и
`02_ДЛЯ_ВАС`; в него не включаются выписки ЕГРЮЛ/ЕГРИП. При незавершённом
пакете возвращается `409` и тот же структурированный список блокирующих пунктов.
Скачивание записывается в аудит как `filing_package.downloaded`.

### PUT `/api/v1/source-documents/{document_id}/kind`

Подтверждает назначение загруженного файла человеком. Принимает конкретный
`document_kind`; значения `unknown` и `unknown_registry_extract` отклоняются.
После решения снимается `kind_requires_confirmation`, сохраняется идентификатор
пользователя и создаётся аудит `document.kind_confirmed`. Только подтверждённые
изображения, доверенности и документы о приоритете включаются в ZIP.

## Изображение обозначения

### POST `/api/v1/applications/{application_id}/mark-image`

Multipart-загрузка PNG/JPEG для `figurative` или `combined`. Проверяет реальный
тип и декодирование изображения, делает файл активным приложением к заявке и
возвращает размер, формат, основные цвета, перцептивный хэш, OCR-текст,
уверенность OCR и явное ограничение визуального поиска.

### GET `/api/v1/applications/{application_id}/mark-image`

Возвращает метаданные активного изображения и распознанный текст. `404`
означает, что действующее изображение не выбрано.

### GET `/api/v1/applications/{application_id}/mark-image/content`

Отдаёт бинарное содержимое для авторизованного предпросмотра. Прямого публичного
URL к файловому хранилищу нет.

### DELETE `/api/v1/applications/{application_id}/mark-image`

Отвязывает активное изображение. Исходная запись сохраняется для аудита, но
меняет назначение и больше не входит в пакет подачи.

### GET `/api/v1/risk-findings/{finding_id}/registry-image`

Возвращает авторизованному пользователю кэшированное изображение карточки,
которое фактически участвовало в визуальном сравнении. Внешний URL Роспатента
не используется фронтендом напрямую. `410` означает, что файловый кэш утрачен
и анализ необходимо повторить.

При анализе комбинированного знака `verification.image_comparison` содержит
общую оценку и компоненты `difference_hash`, `average_hash`,
`color_histogram`, `aspect_ratio`, а также версию метода. Визуальная оценка
может повысить приоритет карточки, но не отменяет проверки специалистом.
