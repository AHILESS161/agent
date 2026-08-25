# Стратегия тестирования системы регистрации товарных знаков

> Архивная целевая спецификация. Актуальные команды и фактические проверки
> находятся в `docs/testing.md`.

> **Статус на 15.08.2026:** целевая стратегия. Реально реализованные наборы,
> команды и известные пробелы перечислены в [`testing.md`](../../testing.md). На дату
> актуализации pytest собирает 704 backend-теста.

> **Версия:** 1.0  
> **Дата:** 2026-03-29

---

## 1. Обзор

Тестирование системы охватывает шесть уровней, от модульных тестов отдельных функций до сквозных E2E-сценариев полного жизненного цикла заявки. Особое внимание уделяется:

- **Промпт-тестированию** — качество и стабильность выходов LLM.
- **Контрактному тестированию** — корректность интеграций (ФИПС, LLM-провайдер).
- **Сквозному тестированию** — 5 обязательных E2E-сценариев, покрывающих критические пути.

### 1.1 Пирамида тестирования

```
                  ┌──────────────┐
                  │    E2E       │  5 сценариев
                  │  (Playwright)│
                ┌─┴──────────────┴─┐
                │  API Integration │  ~80 тестов
                │  (pytest + httpx)│
              ┌─┴──────────────────┴─┐
              │   Provider Contract  │  ~20 тестов
              │   (Pact / schemathesis│
            ┌─┴────────────────────────┴─┐
            │      Prompt Contract       │  ~30 тестов
            │   (LLM output validation)  │
          ┌─┴──────────────────────────────┴─┐
          │          Unit Tests              │  ~300+ тестов
          │  (pytest, coverage ≥ 80%)        │
          └──────────────────────────────────┘
```

---

## 2. Модульные тесты (Unit Tests)

### 2.1 Что тестируется

| Компонент | Что проверяется | Инструмент |
|---|---|---|
| Машина состояний | `can_transition()`, все валидные/невалидные переходы | pytest |
| Доменные правила | Инварианты сущностей, валидация ИНН/ОГРН | pytest |
| Маппинг полей документов | `FieldExtractor.extract()` для каждого шаблона | pytest |
| PII-маскирование | Корректность маскировки для каждого паттерна | pytest |
| Chunking стратегия | Разбивка на чанки по границам статей | pytest |
| Confidence scoring | Формула `ConfidenceScorer.compute()` | pytest |
| Rate limit логика | Подсчёт запросов, сброс окна | pytest |
| JWT создание/валидация | Генерация токенов, проверка claims | pytest |

### 2.2 Структура тестов

```
backend/
└── tests/
    ├── unit/
    │   ├── applications/
    │   │   ├── test_state_machine.py
    │   │   ├── test_application_service.py
    │   │   └── test_application_validators.py
    │   ├── documents/
    │   │   ├── test_field_extractor.py
    │   │   ├── test_completeness_checker.py
    │   │   ├── test_docx_renderer.py
    │   │   └── test_quality_checker.py
    │   ├── rag/
    │   │   ├── test_chunker.py
    │   │   ├── test_hybrid_retriever.py
    │   │   └── test_confidence_scorer.py
    │   ├── security/
    │   │   ├── test_pii_masker.py
    │   │   ├── test_jwt_handler.py
    │   │   └── test_rbac.py
    │   └── agents/
    │       ├── test_intake_validator.py
    │       └── test_state.py
    ├── integration/
    ├── contract/
    └── e2e/
```

### 2.3 Примеры модульных тестов

```python
# backend/tests/unit/applications/test_state_machine.py
# Тесты машины состояний заявки

import pytest
from app.applications.domain.state_machine import (
    ApplicationStatus, can_transition, VALID_TRANSITIONS, TERMINAL_STATUSES
)

class TestStateMachineTransitions:
    """Тесты допустимых и недопустимых переходов состояний."""
    
    @pytest.mark.parametrize("from_status,to_status,expected", [
        # Допустимые переходы
        (ApplicationStatus.DRAFT, ApplicationStatus.INTAKE_REVIEW, True),
        (ApplicationStatus.DRAFT, ApplicationStatus.AWAITING_CLIENT_DATA, True),
        (ApplicationStatus.INTAKE_REVIEW, ApplicationStatus.LEGAL_PRECHECK_RUNNING, True),
        (ApplicationStatus.AWAITING_LAWYER_REVIEW, ApplicationStatus.CLASSES_REVIEW, True),
        (ApplicationStatus.READY_FOR_SUBMISSION, ApplicationStatus.SUBMITTED, True),
        
        # Недопустимые переходы
        (ApplicationStatus.DRAFT, ApplicationStatus.SUBMITTED, False),
        (ApplicationStatus.COMPLETED, ApplicationStatus.DRAFT, False),
        (ApplicationStatus.ARCHIVED, ApplicationStatus.DRAFT, False),
        (ApplicationStatus.SUBMITTED, ApplicationStatus.DRAFT, False),
        (ApplicationStatus.LEGAL_PRECHECK_RUNNING, ApplicationStatus.DOCS_PREPARATION, False),
    ])
    def test_transition(self, from_status, to_status, expected):
        assert can_transition(from_status, to_status) == expected
    
    def test_all_terminal_statuses_have_no_outgoing_transitions_except_archived(self):
        """Проверка: из terminal status нельзя перейти назад (только в archived)."""
        for status in TERMINAL_STATUSES:
            if status == ApplicationStatus.ARCHIVED:
                assert VALID_TRANSITIONS[status] == []
            else:
                allowed = VALID_TRANSITIONS.get(status, [])
                assert allowed == [ApplicationStatus.ARCHIVED], \
                    f"Из {status} разрешены только переходы в archived, получено: {allowed}"
    
    def test_complete_happy_path_is_reachable(self):
        """Проверка: счастливый путь до completed достижим."""
        happy_path = [
            ApplicationStatus.DRAFT,
            ApplicationStatus.INTAKE_REVIEW,
            ApplicationStatus.LEGAL_PRECHECK_RUNNING,
            ApplicationStatus.AWAITING_LAWYER_REVIEW,
            ApplicationStatus.CLASSES_REVIEW,
            ApplicationStatus.CONFLICT_SEARCH_RUNNING,
            ApplicationStatus.RECOMMENDATION_READY,
            ApplicationStatus.DOCS_PREPARATION,
            ApplicationStatus.AWAITING_DOC_APPROVAL,
            ApplicationStatus.READY_FOR_SUBMISSION,
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.STATUS_MONITORING,
            ApplicationStatus.COMPLETED,
        ]
        for i in range(len(happy_path) - 1):
            assert can_transition(happy_path[i], happy_path[i + 1]), \
                f"Переход {happy_path[i]} → {happy_path[i+1]} должен быть допустимым"


class TestPIIMasker:
    """Тесты маскирования персональных данных."""
    
    def test_inn_10_digits_masked(self):
        masker = PIIMasker()
        result = masker.mask_string("ИНН заявителя: 7712345678, адрес: Москва")
        assert "7712345678" not in result
        assert "771" in result  # Первые 3 цифры сохраняются
    
    def test_email_masked(self):
        masker = PIIMasker()
        result = masker.mask_string("Адрес: example.user@company.ru")
        assert "example.user@company.ru" not in result
        assert "@company.ru" in result
    
    def test_phone_masked(self):
        masker = PIIMasker()
        result = masker.mask_string("Тел.: +7 (495) 123-45-67")
        assert "+7 (495) 123-45-67" not in result
```

### 2.4 Цели покрытия

| Слой | Минимальное покрытие |
|---|---|
| Domain layer | 90% |
| Services layer | 80% |
| Infrastructure layer | 70% |
| API layer (schemas, validators) | 80% |
| **Итоговое покрытие** | **≥ 80%** |

---

## 3. Интеграционные тесты API (API Integration Tests)

### 3.1 Подход

- **Инструменты:** `pytest` + `httpx.AsyncClient` + тестовая БД (SQLite in-memory или PostgreSQL в Docker).
- LLM-вызовы: **всегда мокируются** через `pytest-mock` / `respx`.
- ФИПС API: **всегда мокируется** через `MockFIPSProvider`.
- Каждый тест изолирован — транзакция откатывается в teardown.

### 3.2 Набор тестов

```python
# backend/tests/integration/test_application_lifecycle.py
# Интеграционные тесты жизненного цикла заявки

@pytest.fixture
async def created_application(client: AsyncClient, lawyer_token: str, sample_client: Client):
    """Фикстура: созданная заявка с тестовыми данными."""
    response = await client.post(
        "/api/v1/applications",
        json={
            "client_id": str(sample_client.id),
            "responsible_lawyer_id": str(lawyer_token.user_id),
            "mark_type": "word",
            "working_title": "Тестовый словесный ТЗ",
            "mark": {"verbal_element": "ТЕСТМАРК"},
            "preliminary_goods_services": ["Программное обеспечение"],
        },
        headers={"Authorization": f"Bearer {lawyer_token.token}"}
    )
    assert response.status_code == 201
    return response.json()["data"]


class TestApplicationAPI:
    
    async def test_create_application_returns_draft_status(self, client, lawyer_token, sample_client):
        response = await client.post("/api/v1/applications", ...)
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "draft"
        assert response.json()["data"]["application_number"].startswith("TZ-")
    
    async def test_client_cannot_create_application(self, client, client_token):
        response = await client.post("/api/v1/applications", ..., 
                                      headers={"Authorization": f"Bearer {client_token}"})
        assert response.status_code == 403
    
    async def test_client_sees_only_own_applications(self, client, client_token, other_client_token):
        # Создаём заявку для другого клиента...
        # Проверяем, что первый клиент её не видит
        response = await client.get("/api/v1/applications",
                                     headers={"Authorization": f"Bearer {client_token}"})
        app_ids = [a["id"] for a in response.json()["data"]]
        assert other_application_id not in app_ids
    
    async def test_validate_triggers_intake_validator_agent(
        self, client, lawyer_token, created_application, mock_agent_runner
    ):
        response = await client.post(
            f"/api/v1/applications/{created_application['id']}/validate",
            headers={"Authorization": f"Bearer {lawyer_token}"}
        )
        assert response.status_code == 202
        assert response.json()["data"]["status"] == "running"
        mock_agent_runner.assert_called_once_with(
            agent_name="intake_validator",
            application_id=created_application["id"]
        )
    
    async def test_legal_review_approve_requires_lawyer_role(self, client, manager_token, app):
        response = await client.post(
            f"/api/v1/applications/{app['id']}/legal-review/approve",
            json={"decision": "approved"},
            headers={"Authorization": f"Bearer {manager_token}"}
        )
        assert response.status_code == 403
    
    async def test_submit_blocked_until_ready_for_submission(self, client, lawyer_token, app):
        # Заявка в статусе draft — подача невозможна
        response = await client.post(
            f"/api/v1/applications/{app['id']}/submit",
            json={"submission_channel": "fips_api", "confirm": True},
            headers={"Authorization": f"Bearer {lawyer_token}"}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "APPLICATION_WRONG_STATUS"
```

---

## 4. Контрактные тесты провайдеров (Provider Contract Tests)

### 4.1 ФИПС API-контракт

```python
# backend/tests/contract/test_fips_provider.py
# Контрактные тесты ФИПС-провайдера (mock и реальный должны совпадать)

class TestFIPSProviderContract:
    """Тесты контракта интерфейса FIPSProvider."""
    
    @pytest.fixture(params=["mock", "real"])
    def provider(self, request):
        if request.param == "mock":
            return MockFIPSProvider()
        else:
            pytest.skip("Реальный ФИПС провайдер недоступен в тестовой среде")
    
    async def test_search_returns_list_of_results(self, provider):
        results = await provider.search(query="ТЕСТ", classes=[9], threshold=0.7)
        assert isinstance(results, list)
        for r in results:
            assert hasattr(r, "trademark_number")
            assert hasattr(r, "similarity_score")
            assert 0.0 <= r.similarity_score <= 1.0
    
    async def test_submit_returns_receipt(self, provider):
        result = await provider.submit(package=MockDocumentPackage())
        assert result.receipt_number is not None
        assert result.status in ["submitted", "acknowledged", "failed"]
    
    async def test_check_status_returns_valid_status(self, provider):
        result = await provider.check_status(request_id="TEST-001")
        assert result.status is not None
        assert result.checked_at is not None
```

### 4.2 LLM-провайдер контракт

```python
# backend/tests/contract/test_llm_provider.py
# Контрактные тесты LLM-провайдера

class TestLLMProviderContract:
    """Проверка, что LLM-провайдер соблюдает контракт."""
    
    async def test_structured_output_returns_valid_json(self, llm_provider):
        """LLM должен возвращать валидный JSON при json_object mode."""
        response = await llm_provider.invoke(
            messages=[{"role": "user", "content": "Верни JSON: {\"test\": true}"}],
            response_format="json_object"
        )
        parsed = json.loads(response.content)
        assert isinstance(parsed, dict)
    
    async def test_response_within_timeout(self, llm_provider):
        """LLM должен ответить в течение 30 секунд."""
        import asyncio
        try:
            async with asyncio.timeout(30):
                response = await llm_provider.invoke(messages=[...])
        except asyncio.TimeoutError:
            pytest.fail("LLM не ответил в течение 30 секунд")
```

---

## 5. Контрактные тесты промптов (Prompt Contract Tests)

Промпт-контракт проверяет, что **конкретная версия промпта** выдаёт корректный структурированный вывод для набора эталонных входов.

```python
# backend/tests/contract/test_prompt_contracts.py
# Тесты контрактов промптов — проверка выходных схем LLM

import pytest
from app.prompts.registry import PromptRegistry
from app.llm.service import LLMService

class TestPromptContracts:
    """Проверка соответствия выходов промптов ожидаемым схемам."""
    
    @pytest.fixture(autouse=True)
    def setup(self, prompt_registry: PromptRegistry, llm_service: LLMService):
        self.registry = prompt_registry
        self.llm = llm_service
    
    @pytest.mark.parametrize("prompt_code,input_vars,expected_schema_class", [
        ("absolute_grounds_check", ABSOLUTE_GROUNDS_TEST_INPUT, AbsoluteGroundsOutput),
        ("relative_grounds_check", RELATIVE_GROUNDS_TEST_INPUT, RelativeGroundsOutput),
        ("nice_classification", NICE_CLASS_TEST_INPUT, NiceClassificationOutput),
        ("conflict_search_query_builder", CONFLICT_QUERY_TEST_INPUT, ConflictSearchQueryBuilderOutput),
        ("conflict_analysis", CONFLICT_ANALYSIS_TEST_INPUT, ConflictAnalysisOutput),
        ("recommendation_synthesis", RECOMMENDATION_TEST_INPUT, RecommendationOutput),
        ("document_field_extraction", DOC_FIELDS_TEST_INPUT, DocumentFieldsOutput),
        ("intake_completeness_check", INTAKE_TEST_INPUT, IntakeCompletenessOutput),
        ("status_event_interpretation", STATUS_TEST_INPUT, StatusEventInterpretationOutput),
        ("human_review_summary", REVIEW_SUMMARY_TEST_INPUT, HumanReviewSummaryOutput),
    ])
    async def test_prompt_output_matches_schema(
        self, 
        prompt_code: str,
        input_vars: dict,
        expected_schema_class: type,
    ):
        """Промпт должен возвращать вывод, валидируемый ожидаемой Pydantic-схемой."""
        
        rendered = self.registry.render(prompt_code, input_vars)
        raw_response = await self.llm.invoke(rendered)
        
        # Не должно быть исключений при парсинге
        output = expected_schema_class.model_validate_json(raw_response.content)
        
        # Базовые инварианты
        if hasattr(output, "confidence"):
            assert 0.0 <= output.confidence <= 1.0
        if hasattr(output, "overall_risk"):
            assert output.overall_risk in ["low", "medium", "high", "blocking"]
    
    async def test_absolute_grounds_blocking_case(self):
        """Описательное обозначение должно получить высокий/блокирующий риск."""
        
        input_vars = {
            "rag_context": ABSOLUTE_GROUNDS_RAG_CONTEXT,
            "mark_type": "word",
            "mark_verbal_element": "ГОРЯЧИЙ",  # Явно описательное слово
            "mark_description": "",
            "applicant_type": "legal_entity",
        }
        
        rendered = self.registry.render("absolute_grounds_check", input_vars)
        raw_response = await self.llm.invoke(rendered)
        output = AbsoluteGroundsOutput.model_validate_json(raw_response.content)
        
        assert output.overall_risk in ["high", "blocking"], \
            f"Описательное обозначение должно получить высокий риск, получено: {output.overall_risk}"
        assert len(output.findings) >= 1
        assert any(f.severity in ["risk", "blocking"] for f in output.findings)
    
    async def test_nice_classification_suggests_valid_classes(self):
        """Классификатор должен предлагать классы в диапазоне 1–45."""
        
        output = NiceClassificationOutput.model_validate_json(
            (await self.llm.invoke(self.registry.render("nice_classification", NICE_CLASS_TEST_INPUT))).content
        )
        
        for suggestion in output.suggestions:
            assert 1 <= suggestion.nice_class <= 45, \
                f"Класс МКТУ {suggestion.nice_class} выходит за допустимый диапазон"
        assert len(output.suggestions) >= 1
```

---

## 6. Сквозные E2E-тесты (End-to-End)

**Инструменты:** Playwright (для UI) + pytest (для прямых API-вызовов).  
**Среда:** Docker Compose с реальным PostgreSQL, Qdrant, моком LLM (детерминированные ответы) и MockFIPSProvider.

### E2E-01: Полный счастливый путь — словесный ТЗ

**Сценарий:** Регистрация словесного ТЗ без конфликтов от создания до подачи в ФИПС.

```gherkin
Сценарий: Успешная регистрация словесного товарного знака
  
  Дано: Юрист залогинен в системе
    И Клиент "ООО Тест" существует в системе
  
  Когда: Менеджер создаёт заявку для "ООО Тест" с обозначением "КВИНТОР" (тип: word)
    И указывает предварительный перечень товаров: "Программное обеспечение, класс 42"
  
  Тогда: Заявка создана со статусом "draft"
  
  Когда: Юрист запускает валидацию заявки (POST /validate)
  Тогда: Статус меняется на "legal_precheck_running"
    И агенты AbsoluteGrounds и RelativeGrounds завершают работу
    И статус меняется на "awaiting_lawyer_review"
    И создан HumanReviewPacket
  
  Когда: Юрист одобряет правовую экспертизу (POST /legal-review/approve, decision=approved)
  Тогда: Статус меняется на "classes_review"
    И агент NiceClassification предлагает классы [42]
  
  Когда: Юрист утверждает классы МКТУ [42] (POST /classes/approve)
  Тогда: Статус меняется на "conflict_search_running"
    И ConflictSearchJob создан и выполнен
    И RecommendationMemo создан с recommendation="proceed"
    И статус меняется на "recommendation_ready"
  
  Когда: Юрист одобряет рекомендацию (POST /recommendation/approve)
  Тогда: Статус меняется на "docs_preparation"
    И DocumentPackage создан со всеми обязательными документами
    И статус меняется на "awaiting_doc_approval"
  
  Когда: Юрист подписывает пакет документов (POST /documents/approve)
  Тогда: Статус меняется на "ready_for_submission"
  
  Когда: Юрист инициирует подачу (POST /submit, confirm=true)
  Тогда: Submission создан с fips_receipt_number заполненным
    И статус меняется на "submitted"
    И затем в "status_monitoring"
    И уведомление отправлено клиенту
    И все события записаны в AuditLog
```

---

### E2E-02: Заявка с неполными данными — запрос клиенту

**Сценарий:** Клиент подаёт заявку без изображения; система запрашивает дополнение, клиент загружает файл.

```gherkin
Сценарий: Запрос недостающих данных от клиента (изображение ТЗ)
  
  Дано: Заявка на комбинированный ТЗ без файла изображения
  
  Когда: Запускается IntakeValidator
  Тогда: Валидатор возвращает missing_fields: ["mark.image_file_path"]
    И статус меняется на "awaiting_client_data"
    И клиент получает уведомление с запросом изображения
  
  Когда: Клиент загружает изображение через API (POST /documents/upload)
    И менеджер повторно запускает валидацию
  Тогда: IntakeValidator возвращает is_complete=true
    И статус меняется в "legal_precheck_running"
    И дальнейший процесс продолжается штатно
```

---

### E2E-03: Блокирующий риск — отказ в регистрации

**Сценарий:** Обозначение содержит государственную символику; агент возвращает блокирующий риск; юрист принимает решение об отказе.

```gherkin
Сценарий: Блокирующее основание — обозначение с элементами государственной символики
  
  Дано: Заявка на регистрацию обозначения "ГОСУДАРСТВО" (тип: word)
  
  Когда: Завершается правовая экспертиза
  Тогда: AbsoluteGrounds возвращает overall_risk="blocking"
    И findings содержит severity="blocking" с article_reference="ст. 1483, п. 4 ГК РФ"
    И HumanReviewPacket отмечает критические находки
  
  Когда: Юрист рассматривает пакет и принимает решение "отказать"
    И вызывает POST /legal-review/approve с decision="rejected"
  Тогда: Статус заявки меняется на "rejected"
    И создана AuditLog запись с action="status_changed" и reason
    И клиент получает уведомление об отказе
    И статус больше не может измениться (кроме "archived")
```

---

### E2E-04: Конфликтный поиск выявляет высокий риск — изменение рекомендации

**Сценарий:** Поиск конфликтов выявляет сходный ТЗ; рекомендация — `proceed_with_modifications`; юрист согласует; документы генерируются с дискламацией.

```gherkin
Сценарий: Конфликт выявлен — рекомендация с модификациями
  
  Дано: Заявка прошла правовую экспертизу и утверждение классов
  
  Когда: ConflictSearchOrchestrator находит конфликт с risk_level="high"
    И ConflictAnalysis оценивает similarity_score >= 0.75
    И Recommendation генерирует recommendation="proceed_with_modifications"
    И proposed_actions содержит "Добавить дискламацию словесного элемента"
  
  Тогда: Статус переходит в "recommendation_ready"
  
  Когда: Юрист одобряет рекомендацию с модификацией
  Тогда: TemplateSelector включает шаблон "disclaimer_request" в пакет
    И DocumentPackage содержит 4 документа вместо 3
    И все 4 документа успешно сгенерированы
    И пакет имеет статус "assembled"
```

---

### E2E-05: Получение Office Action от ФИПС — ответ клиента

**Сценарий:** После подачи ФИПС присылает запрос на экспертизу; система уведомляет юриста; юрист подготавливает ответ.

```gherkin
Сценарий: Получение запроса ФИПС (Office Action) и ответ на него
  
  Дано: Заявка в статусе "status_monitoring"
    И Submission.fips_receipt_number = "2026100042"
  
  Когда: ФИПС отправляет webhook POST /webhooks/fips с event_type="STATUS_CHANGE"
    И new_status="OFFICE_ACTION_RECEIVED"
    И в payload: требование предоставить уточнение перечня товаров
  
  Тогда: Создан SubmissionStatusEvent с event_type="office_action"
    И requires_client_action=true
    И action_deadline устанавливается на +90 дней
    И статус заявки переходит в "office_action_received"
    И юрист и менеджер получают уведомления
  
  Когда: Юрист инициирует подготовку ответа
    И статус меняется в "client_action_required"
  
  Когда: Клиент подтверждает уточнённый перечень товаров
    И юрист формирует ответный пакет документов
    И пакет одобряется (POST /documents/approve)
  
  Тогда: Новый Submission создан для ответа на OA
    И статус возвращается в "status_monitoring"
    И deadline очищается
    И AuditLog фиксирует все действия
```

---

## 7. Тестирование RAG-конвейера

### 7.1 Тесты ингестии

```python
# backend/tests/integration/test_rag_ingestion.py

class TestRAGIngestion:
    
    async def test_ingest_gk_rf_part4_creates_chunks(self, rag_service):
        result = await rag_service.ingest_source(source_id=GK_RF_SOURCE_ID)
        
        assert result.chunks_created > 0
        assert result.errors == []
        
        # Проверяем ключевые статьи
        chunks = await rag_service.search_chunks(
            query="статья 1483 основания отказа",
            source_codes=["gk_rf_part4"]
        )
        assert len(chunks) >= 3
        assert any("1483" in chunk.article_reference for chunk in chunks)
    
    async def test_chunks_have_valid_embeddings(self, db_session):
        chunks = await KnowledgeChunkRepository(db_session).get_by_source("gk_rf_part4")
        for chunk in chunks[:10]:  # Проверяем первые 10
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1024  # multilingual-e5-large
    
    async def test_retrieval_finds_relevant_articles(self, rag_service):
        results = await rag_service.retrieve_for_agent(
            query="описательность обозначения",
            agent_type=AgentType.ABSOLUTE_GROUNDS
        )
        
        assert len(results.chunks) >= 3
        assert results.coverage_score >= 0.6
        article_refs = [c.article_reference for c in results.chunks]
        assert any("1483" in ref for ref in article_refs)
```

---

## 8. Конфигурация CI/CD

```yaml
# .github/workflows/test.yml
# Конфигурация тестирования в CI/CD

name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Запуск модульных тестов
        run: |
          cd backend
          pip install -r requirements-test.txt
          pytest tests/unit/ -v --cov=app --cov-report=xml --cov-fail-under=80
      - uses: codecov/codecov-action@v4

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
    steps:
      - name: Запуск интеграционных тестов
        run: pytest tests/integration/ -v
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost/test_db
          LLM_PROVIDER: mock

  prompt-contract-tests:
    runs-on: ubuntu-latest
    # Только на ветках main и release (дорогие тесты с реальным LLM)
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/heads/release')
    services:
      ollama:
        image: ollama/ollama:latest
    steps:
      - name: Загрузка LLM-модели
        run: ollama pull huihui_ai/qwen2.5-abliterate:14b
      - name: Запуск контрактных тестов промптов
        run: pytest tests/contract/test_prompt_contracts.py -v --timeout=120
        env:
          LLM_PROVIDER: ollama
          LLM_BASE_URL: http://localhost:11434

  e2e-tests:
    runs-on: ubuntu-latest
    # Только на main ветке
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Запуск E2E в Docker Compose
        run: |
          docker-compose -f docker-compose.test.yml up -d
          pytest tests/e2e/ -v --timeout=300
          docker-compose -f docker-compose.test.yml down
```

---

## 9. Тестовые фикстуры и фабрики

```python
# backend/tests/factories.py
# Фабрики тестовых данных

import factory
from factory.alchemy import SQLAlchemyModelFactory

class ClientFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Client
        sqlalchemy_session = db_session
    
    client_type = "legal_entity"
    short_name = factory.Faker("company", locale="ru_RU")
    full_legal_name = factory.LazyAttribute(lambda o: f"ООО «{o.short_name}»")
    inn = factory.Faker("numerify", text="##########")  # 10 цифр
    email = factory.Faker("email")
    is_active = True

class TrademarkApplicationDraftFactory(SQLAlchemyModelFactory):
    class Meta:
        model = TrademarkApplicationDraft
    
    application_number = factory.Sequence(lambda n: f"TZ-2026-{n:05d}")
    status = ApplicationStatus.DRAFT
    mark_type = "word"
    working_title = factory.Faker("sentence", locale="ru_RU", nb_words=4)
    client = factory.SubFactory(ClientFactory)
```

---

## 10. Сводка требований к тестированию

| Уровень | Инструмент | Покрытие / Кол-во | Запуск в CI |
|---|---|---|---|
| Unit | pytest | ≥ 80% coverage | При каждом push |
| API Integration | pytest + httpx | ~80 тестов | При каждом push |
| Provider Contract | pytest + Pact | ~20 тестов | При каждом push |
| Prompt Contract | pytest + LLM | ~30 тестов | Только main/release |
| E2E | Playwright + pytest | 5 сценариев | Только main |
| **Обязательные для релиза** | **Все уровни** | **100% pass** | **Перед деплоем** |
