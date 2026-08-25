# Реестр промптов системы регистрации товарных знаков

> Архивная проектная спецификация. Источником правды для действующих промптов
> являются YAML-файлы и их тесты в `backend/prompts/`.

> **Статус на 15.08.2026:** архитектурная спецификация плюс частично реализованный
> YAML-реестр. Фактические активные промпты находятся в `backend/prompts`; не все
> процессы и тест-кейсы из этого документа реализованы.

> **Версия:** 1.0  
> **Дата:** 2026-03-29

---

## 1. Обзор

Реестр промптов — централизованное хранилище всех промптов, используемых LLM-агентами системы. Ключевые принципы:

- **Версионирование** — каждое изменение промпта создаёт новую версию; активная версия фиксируется явно.
- **Аудируемость** — каждое использование промпта логируется с его версией.
- **Разделение кода и промптов** — изменение промпта не требует редеплоя кода.
- **Тестируемость** — каждый промпт имеет тест-кейсы для регрессионного тестирования.

---

## 2. YAML-спецификация формата промпта

```yaml
# Пример файла промпта: prompts/absolute_grounds_check/v1.2.yaml

# ─── Метаданные ────────────────────────────────────────────────────────────────
prompt_code: "absolute_grounds_check"
version: "1.2"
name_ru: "Проверка абсолютных оснований отказа"
description_ru: |
  Проверяет обозначение на абсолютные основания для отказа в регистрации
  согласно ст. 1483, пп. 1–8 ГК РФ. Использует контекст из базы знаний
  для обоснования каждого вывода ссылкой на конкретную норму права.
status: "active"  # draft | active | deprecated | archived
created_at: "2026-02-15T10:00:00Z"
updated_at: "2026-03-20T14:30:00Z"
created_by: "admin@firm.ru"
changelog: |
  v1.2 (2026-03-20): Добавлены примеры «правильного» вывода (few-shot).
                     Улучшено форматирование ссылок на статьи.
  v1.1 (2026-02-20): Уточнены инструкции по оценке цвета и формы.
  v1.0 (2026-02-15): Первоначальная версия.

# ─── Параметры модели ───────────────────────────────────────────────────────────
model_override: null  # null = использовать модель по умолчанию из конфигурации
temperature: 0.1      # Низкая для детерминизма правовых выводов
max_tokens: 4096
response_format: "json_object"  # Обязательный JSON mode

# ─── Входные переменные ─────────────────────────────────────────────────────────
input_variables:
  rag_context:
    type: "string"
    description: "Релевантные чанки из базы правовых знаний"
    required: true
    max_length: 8000
  mark_verbal_element:
    type: "string"
    description: "Словесный элемент обозначения"
    required: false
  mark_description:
    type: "string"
    description: "Описание изображения (для изобразительных ТЗ)"
    required: false
  mark_type:
    type: "string"
    enum: ["word", "figurative", "combined", "3d", "sound", "color"]
    required: true
  applicant_type:
    type: "string"
    enum: ["individual", "legal_entity", "sole_proprietor"]
    required: true

# ─── JSON-схема выхода ──────────────────────────────────────────────────────────
output_schema:
  type: "object"
  required: ["findings", "overall_risk", "summary_ru", "confidence"]
  properties:
    findings:
      type: "array"
      description: "Список правовых выводов"
      items:
        type: "object"
        required: ["ground_code", "article_reference", "severity", "description_ru"]
        properties:
          ground_code:
            type: "string"
            description: "Код основания, напр. ABS_1483_1_1"
          article_reference:
            type: "string"
            description: "Ссылка на норму права"
          severity:
            type: "string"
            enum: ["info", "warning", "risk", "blocking"]
          description_ru:
            type: "string"
            description: "Описание на русском языке"
          recommendation_ru:
            type: "string"
            description: "Рекомендация по устранению"
          confidence:
            type: "number"
            minimum: 0.0
            maximum: 1.0
          rag_citation_ids:
            type: "array"
            items:
              type: "string"
              description: "ID чанка базы знаний"
    overall_risk:
      type: "string"
      enum: ["low", "medium", "high", "blocking"]
    summary_ru:
      type: "string"
      maxLength: 1000
    confidence:
      type: "number"
      minimum: 0.0
      maximum: 1.0
    insufficient_rag_coverage:
      type: "boolean"
      default: false

# ─── Шаблон промпта ─────────────────────────────────────────────────────────────
system_prompt: |
  Ты — ИИ-ассистент российской юридической фирмы, специализирующейся на
  регистрации товарных знаков. Твоя задача — проверить обозначение на
  абсолютные основания для отказа в регистрации по ст. 1483 ГК РФ.

  ПРАВИЛА:
  1. Основывай КАЖДЫЙ вывод ТОЛЬКО на предоставленном контексте из базы знаний.
  2. Если информации недостаточно — укажи это явно (insufficient_rag_coverage: true).
  3. Цитируй конкретные нормы права (ст. X, п. Y ГК РФ).
  4. Отвечай ИСКЛЮЧИТЕЛЬНО на русском языке.
  5. Ответ должен быть строго в формате JSON согласно схеме.
  6. НЕ делай выводов, не подкреплённых контекстом.

user_prompt: |
  ## Контекст из базы правовых знаний
  {rag_context}

  ---

  ## Данные проверяемого обозначения
  - Тип обозначения: {mark_type}
  - Словесный элемент: {mark_verbal_element}
  - Описание: {mark_description}
  - Тип заявителя: {applicant_type}

  ---

  Проведи проверку на абсолютные основания для отказа в регистрации.
  Верни результат строго в формате JSON согласно описанной схеме.

  ## Примеры правильных выводов (few-shot)

  ### Пример 1: Описательное обозначение
  Обозначение: «СВЕЖИЙ» для класса 29 (молочные продукты)
  ```json
  {
    "findings": [{
      "ground_code": "ABS_1483_1_3",
      "article_reference": "ст. 1483, п. 1, пп. 3 ГК РФ",
      "severity": "blocking",
      "description_ru": "Обозначение «СВЕЖИЙ» является описательным...",
      "recommendation_ru": "Рекомендуется изменить обозначение...",
      "confidence": 0.92,
      "rag_citation_ids": ["chunk-abc-123"]
    }],
    "overall_risk": "blocking",
    "summary_ru": "Обозначение не может быть зарегистрировано...",
    "confidence": 0.92,
    "insufficient_rag_coverage": false
  }
  ```

# ─── Тест-кейсы ─────────────────────────────────────────────────────────────────
test_cases:
  - name: "Описательное словесное обозначение"
    input:
      mark_type: "word"
      mark_verbal_element: "ГОРЯЧИЙ"
      mark_description: null
      applicant_type: "legal_entity"
    expected:
      overall_risk_in: ["high", "blocking"]
      findings_min_count: 1
      findings_severity_contains: ["blocking", "risk"]
  
  - name: "Государственная символика"
    input:
      mark_type: "combined"
      mark_verbal_element: "ГОСТ"
      mark_description: "Комбинированное обозначение с элементами государственной символики"
      applicant_type: "legal_entity"
    expected:
      overall_risk: "blocking"
      findings_contains_ground_code_prefix: "ABS_1483"
  
  - name: "Оригинальное обозначение без оснований"
    input:
      mark_type: "word"
      mark_verbal_element: "КВИНТОР"
      mark_description: null
      applicant_type: "legal_entity"
    expected:
      overall_risk_in: ["low", "medium"]
      insufficient_rag_coverage: false
```

---

## 3. Реестр загрузчика

```python
# backend/app/prompts/registry.py
# Загрузчик реестра промптов из YAML-файлов и/или БД

import yaml
from pathlib import Path
from functools import lru_cache

class PromptRegistry:
    """Реестр промптов с поддержкой версионирования и кэширования."""
    
    _prompts: dict[str, PromptDefinition] = {}
    
    def __init__(
        self,
        yaml_dir: Path,
        db_repo: PromptRepository,
        use_db_override: bool = True,
    ):
        self._yaml_dir = yaml_dir
        self._db_repo = db_repo
        self._use_db_override = use_db_override
    
    async def load_all(self) -> None:
        """Загружает все промпты из YAML (базовые) и БД (переопределения)."""
        
        # 1. Загрузка из YAML-файлов (базовые, из репозитория)
        for yaml_file in self._yaml_dir.rglob("*.yaml"):
            prompt = self._load_from_yaml(yaml_file)
            self._prompts[prompt.prompt_code] = prompt
        
        # 2. Переопределения из БД (управляемые через admin UI)
        if self._use_db_override:
            db_prompts = await self._db_repo.get_all_active()
            for db_prompt in db_prompts:
                # DB версия имеет приоритет над YAML
                self._prompts[db_prompt.prompt_code] = db_prompt
    
    def get(self, prompt_code: str) -> PromptDefinition:
        """Получение активного промпта по коду."""
        if prompt_code not in self._prompts:
            raise PromptNotFoundError(f"Промпт '{prompt_code}' не найден в реестре")
        return self._prompts[prompt_code]
    
    def render(self, prompt_code: str, variables: dict) -> RenderedPrompt:
        """Рендеринг промпта с подстановкой переменных."""
        prompt = self.get(prompt_code)
        
        # Валидация входных переменных
        self._validate_variables(prompt, variables)
        
        return RenderedPrompt(
            system=prompt.system_prompt.format(**variables),
            user=prompt.user_prompt.format(**variables),
            model_override=prompt.model_override,
            temperature=prompt.temperature,
            max_tokens=prompt.max_tokens,
            response_format=prompt.response_format,
            prompt_code=prompt_code,
            prompt_version=prompt.version,
        )
```

---

## 4. Стратегия версионирования

### 4.1 Правила версий (semver-like)

| Тип изменения | Версия | Пример |
|---|---|---|
| Исправление опечатки, без изменения логики | Patch: X.Y.**Z** | 1.2.0 → 1.2.1 |
| Уточнение инструкций, добавление few-shot примеров | Minor: X.**Y**.0 | 1.2 → 1.3 |
| Изменение схемы вывода, переработка структуры | Major: **X**.0.0 | 1.x → 2.0 |

### 4.2 Хранение версий

```
prompts/
├── absolute_grounds_check/
│   ├── v1.0.yaml   # Архивная
│   ├── v1.1.yaml   # Архивная
│   └── v1.2.yaml   # Активная (симлинк current.yaml → v1.2.yaml)
├── relative_grounds_check/
│   └── v1.0.yaml   # Активная
└── ...
```

### 4.3 A/B-тестирование промптов

```python
class PromptABConfig(BaseModel):
    prompt_code: str
    variant_a_version: str    # Контрольная версия
    variant_b_version: str    # Тестируемая версия
    traffic_split: float = 0.1  # 10% трафика на B
    
# При каждом вызове агента:
def select_prompt_version(config: PromptABConfig, run_id: UUID) -> str:
    """Детерминированное разделение трафика на основе run_id."""
    hash_val = int(hashlib.md5(str(run_id).encode()).hexdigest(), 16)
    use_b = (hash_val % 100) < (config.traffic_split * 100)
    return config.variant_b_version if use_b else config.variant_a_version
```

---

## 5. Все 10 обязательных промптов

### PROMPT-01: absolute_grounds_check
**Код:** `absolute_grounds_check`  
**Агент:** AbsoluteGrounds  
**Назначение:** Проверка абсолютных оснований отказа (ст. 1483, пп. 1–8 ГК РФ)  
**Температура:** 0.1  
**Входные переменные:** `rag_context`, `mark_verbal_element`, `mark_description`, `mark_type`, `applicant_type`  
**Выходная схема:** `AbsoluteGroundsOutput`  

---

### PROMPT-02: relative_grounds_check
**Код:** `relative_grounds_check`  
**Агент:** RelativeGrounds  
**Назначение:** Проверка относительных оснований отказа: сходство с ранее зарегистрированными ТЗ (ст. 1483, пп. 6–8 ГК РФ)  
**Температура:** 0.1  
**Входные переменные:** `rag_context`, `mark_verbal_element`, `mark_description`, `mark_type`, `requested_classes`  
**Выходная схема:** `RelativeGroundsOutput`

---

### PROMPT-03: nice_classification
**Код:** `nice_classification`  
**Агент:** NiceClassification  
**Назначение:** Предложение оптимального перечня классов МКТУ и товаров/услуг  
**Температура:** 0.2  
**Входные переменные:** `rag_context`, `mark_type`, `mark_verbal_element`, `preliminary_goods_services`, `business_description`  
**Выходная схема:** `NiceClassificationOutput`

---

### PROMPT-04: conflict_search_query_builder
**Код:** `conflict_search_query_builder`  
**Агент:** ConflictSearchQueryBuilder  
**Назначение:** Генерация поисковых запросов для поиска конфликтующих обозначений в базе ФИПС  
**Температура:** 0.15  
**Входные переменные:** `mark_verbal_element`, `mark_description`, `mark_type`, `approved_classes`  
**Выходная схема:** `ConflictSearchQueryBuilderOutput`

---

### PROMPT-05: conflict_analysis
**Код:** `conflict_analysis`  
**Агент:** ConflictAnalysis  
**Назначение:** Анализ сходства найденных конфликтующих ТЗ с заявляемым обозначением  
**Температура:** 0.1  
**Входные переменные:** `rag_context`, `mark_verbal_element`, `mark_description`, `mark_type`, `approved_classes`, `conflict_results_json`  
**Выходная схема:** `ConflictAnalysisOutput`

---

### PROMPT-06: recommendation_synthesis
**Код:** `recommendation_synthesis`  
**Агент:** Recommendation  
**Назначение:** Синтез итоговой рекомендации на основе результатов правовой экспертизы и поиска конфликтов  
**Температура:** 0.25  
**Входные переменные:** `rag_context`, `legal_review_summary`, `conflict_analysis_summary`, `mark_verbal_element`, `mark_type`, `client_type`  
**Выходная схема:** `RecommendationOutput`  
**Особенности:** Повышенная температура для генерации связного executive summary. Два уровня текста: технический (для юриста) и нетехнический (для клиента).

---

### PROMPT-07: document_field_extraction
**Код:** `document_field_extraction`  
**Агент:** DocumentAssembly  
**Назначение:** Извлечение и форматирование значений полей для заполнения DOCX-шаблонов  
**Температура:** 0.05  
**Входные переменные:** `template_required_fields`, `application_data_json`, `client_data_json`  
**Выходная схема:** `DocumentFieldsOutput`  
**Особенности:** Минимальная температура — чистое извлечение данных, никакой генерации.

---

### PROMPT-08: intake_completeness_check
**Код:** `intake_completeness_check`  
**Агент:** IntakeValidator  
**Назначение:** LLM-ассист для оценки семантической полноты описания обозначения (когда формальные поля заполнены, но содержательно недостаточны)  
**Температура:** 0.1  
**Входные переменные:** `mark_verbal_element`, `mark_description`, `mark_type`, `goods_services_list`  
**Выходная схема:** `IntakeCompletenessOutput`  
**Особенности:** Используется ТОЛЬКО для дополнительной семантической проверки; первичная валидация — детерминированная.

---

### PROMPT-09: status_event_interpretation
**Код:** `status_event_interpretation`  
**Агент:** StatusMonitoring  
**Назначение:** Интерпретация уведомлений ФИПС на естественном языке для отображения клиенту  
**Температура:** 0.3  
**Входные переменные:** `fips_status_code`, `fips_message_ru`, `application_context`  
**Выходная схема:** `StatusEventInterpretationOutput`  
**Особенности:** Перевод технического языка ФИПС в понятный для клиента текст.

---

### PROMPT-10: human_review_summary
**Код:** `human_review_summary`  
**Агент:** HumanReviewPacket  
**Назначение:** Формирование краткого структурированного резюме для юриста по текущей контрольной точке HITL  
**Температура:** 0.2  
**Входные переменные:** `checkpoint_type`, `agent_outputs_summary`, `key_findings`, `recommended_actions`  
**Выходная схема:** `HumanReviewSummaryOutput`  
**Особенности:** Адаптирует уровень детализации под тип чекпоинта (1–4).

---

## 6. Контроль качества промптов

### 6.1 Перед активацией новой версии

- [ ] Ручное тестирование на 5+ реальных кейсах
- [ ] Прохождение всех `test_cases` из YAML-спецификации
- [ ] Проверка корректности JSON-схемы выхода
- [ ] Ревью изменений другим юристом (для промптов PROMPT-01..06)
- [ ] A/B тест на 10% трафика в течение 3 дней

### 6.2 Мониторинг в продакшене

| Метрика | Описание | Порог алерта |
|---|---|---|
| `prompt_json_parse_error_rate` | Доля ответов, не соответствующих JSON-схеме | > 5% |
| `prompt_confidence_avg` | Средняя уверенность по промпту | < 0.5 |
| `prompt_latency_p95` | P95 время LLM-ответа | > 30 сек |
| `prompt_rag_fallback_rate` | Доля запросов в fallback-режиме | > 15% |
