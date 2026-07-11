# Дизайн RAG-конвейера системы правовых знаний

> **Версия:** 1.0  
> **Дата:** 2026-03-29

---

## 1. Обзор

RAG (Retrieval-Augmented Generation) обеспечивает агентов релевантным правовым контекстом из структурированной базы знаний. Без RAG агенты работают только на параметрических знаниях LLM, что неприемлемо для юридически точных выводов.

**Цели RAG-системы:**
- Снизить вероятность галлюцинаций LLM за счёт контекстной привязки.
- Обеспечить цитирование источников в каждом правовом выводе.
- Позволить обновлять правовую базу без переобучения модели.
- Поддерживать confidence scoring для оценки надёжности ответов.

---

## 2. Источники знаний

### 2.1 Начальная база (MVP+)

| Источник | Код | Тип | Описание | Приоритет |
|---|---|---|---|---|
| ГК РФ, Часть IV | `gk_rf_part4` | `law_text` | Гл. 69–77: интеллектуальные права; гл. 76: ТЗ | Критический |
| Приказ Роспатента № 8 от 20.01.2020 | `rospatent_order_8_2020` | `regulation` | Требования к документам заявки | Критический |
| Руководство по регистрации ТЗ (Роспатент) | `rospatent_guideline_tz` | `guideline` | Официальное руководство по процедуре | Высокий |
| Рекомендации Роспатента по МКТУ | `rospatent_mktu_guide` | `guideline` | Классификация товаров и услуг | Высокий |
| МКТУ Алфавитный указатель (рус.) | `mktu_alpha_index` | `guideline` | Перечень товаров/услуг по классам | Высокий |
| Методология фирмы (внутренняя) | `firm_methodology_v1` | `internal_methodology` | Внутренние критерии оценки рисков | Средний |
| Практика отказов ФИПС (обезличенная) | `fips_refusal_cases` | `case_law` | Примеры отказных решений | Средний |

### 2.2 Расширенная база (Post-MVP)

| Источник | Тип | Описание |
|---|---|---|
| База данных правовых актов (Гарант / КонсультантПлюс) | `law_text` | Подключение через API (лицензия) |
| Практика Суда по интеллектуальным правам (СИП) | `case_law` | Решения суда по спорам о ТЗ |
| WIPO Lex — международные нормы | `regulation` | Мадридская система, Парижская конвенция |
| Обновления МКТУ | `guideline` | Новые редакции классификатора |

---

## 3. Конвейер ингестии

```mermaid
flowchart LR
    subgraph SOURCES[Источники]
        PDF[PDF / DOCX\nдокументы]
        TXT[Текстовые файлы\n.txt / .md]
        URL[Веб-страницы\n(Роспатент.ru)]
    end

    subgraph INGESTION[Конвейер ингестии]
        LOAD[1. Загрузчик\nDocumentLoader]
        CLEAN[2. Очистка текста\nTextCleaner]
        META[3. Извлечение метаданных\nMetadataExtractor]
        CHUNK[4. Разбивка на чанки\nChunkSplitter]
        EMBED[5. Векторизация\nEmbeddingModel]
        STORE[6. Сохранение\nVectorStore + RDBMS]
    end

    subgraph OUTPUT[Хранилище]
        VS[(pgvector /\nQdrant)]
        DB[(PostgreSQL\nKnowledgeChunk)]
    end

    PDF --> LOAD
    TXT --> LOAD
    URL --> LOAD
    LOAD --> CLEAN --> META --> CHUNK --> EMBED --> STORE
    STORE --> VS
    STORE --> DB
```

### 3.1 Загрузчики (DocumentLoader)

| Тип файла | Загрузчик | Особенности |
|---|---|---|
| PDF | `PyMuPDFLoader` | Сохраняет номера страниц |
| DOCX | `Docx2txtLoader` | Сохраняет структуру заголовков |
| HTML / веб | `BeautifulSoupLoader` | Извлечение основного текста, удаление навигации |
| TXT / MD | `TextLoader` | Прямая загрузка с кодировкой UTF-8 |

### 3.2 Очистка текста (TextCleaner)

```python
# backend/app/rag/pipeline/cleaner.py
# Функции очистки правового текста перед разбивкой на чанки

def clean_legal_text(text: str) -> str:
    """Нормализация правового текста для индексации."""
    # Удаление колонтитулов и нумерации страниц
    text = remove_headers_footers(text)
    # Нормализация пробелов и переносов строк
    text = normalize_whitespace(text)
    # Нормализация кавычек к единому стилю («»)
    text = normalize_quotes(text)
    # Удаление служебных символов
    text = remove_control_chars(text)
    # Сохранение разметки статей (ст. X, п. Y, пп. Z)
    text = preserve_legal_references(text)
    return text
```

### 3.3 Извлечение метаданных (MetadataExtractor)

Каждый документ обогащается метаданными перед разбивкой:

```python
class DocumentMetadata(BaseModel):
    source_code: str          # Идентификатор источника
    source_type: str          # law_text | regulation | guideline | ...
    document_title: str       # Название документа
    article_reference: str    # Ссылка на статью (если извлечена)
    section_title: str        # Заголовок раздела/главы
    effective_date: date      # Дата вступления в силу
    page_number: int | None   # Номер страницы
    nice_classes: list[int]   # Связанные классы МКТУ (если применимо)
    legal_topics: list[str]   # Теги правовых тем (напр.: absolute_grounds, classification)
```

**Автоматическое тегирование правовых тем:**
- Ключевые слова → теги: «обманный» → `absolute_grounds`; «ранее зарегистрированный» → `relative_grounds`; «класс» + число → `classification`.
- LLM-ассист для документов без очевидных ключевых слов (при ингестии).

### 3.4 Стратегия разбивки на чанки (Chunking)

Используется **иерархическая** стратегия:

| Тип документа | Стратегия | Размер чанка | Перекрытие |
|---|---|---|---|
| Нормативные акты (ГК РФ) | По статьям + по абзацам | 512–768 токенов | 64 токена |
| Руководства Роспатента | По разделам | 768–1024 токенов | 128 токенов |
| МКТУ-указатель | По позициям класса | 256–512 токенов | 32 токена |
| Практика отказов | По решению целиком | 1024–2048 токенов | 128 токенов |
| Внутренняя методология | По параграфам | 512 токенов | 64 токена |

**Приоритет:** Разбивка по границам статей/пунктов (regex `ст\. \d+`, `п\. \d+`) над размерными ограничениями.

```python
# backend/app/rag/pipeline/splitter.py
# Разбивка правовых текстов с сохранением границ статей

from langchain.text_splitter import RecursiveCharacterTextSplitter

LEGAL_SEPARATORS = [
    "\nСтатья ",   # Начало статьи ГК
    "\nст. ",
    "\n\d+\. ",    # Нумерованные пункты
    "\nПункт ",
    "\n\n",
    "\n",
    " ",
]

def create_legal_splitter(chunk_size: int = 768, chunk_overlap: int = 64):
    return RecursiveCharacterTextSplitter(
        separators=LEGAL_SEPARATORS,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=count_tokens,  # Подсчёт токенов, не символов
        keep_separator=True,
    )
```

---

## 4. Векторное хранилище и модель эмбеддингов

### 4.1 Модель эмбеддингов

| Параметр | Значение |
|---|---|
| **Модель (MVP)** | `intfloat/multilingual-e5-large` |
| **Размерность** | 1024 |
| **Языки** | Русский + English (мультиязычная) |
| **Хостинг** | Локально через Ollama / HuggingFace Transformers |
| **Запасная модель** | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (768 dim) |

**Обоснование выбора:** `multilingual-e5-large` показывает высокое качество на русскоязычных правовых текстах без необходимости дообучения. Локальный хостинг исключает утечку клиентских данных.

### 4.2 Конфигурация векторного хранилища

**MVP:** `pgvector` (расширение PostgreSQL)

```sql
-- Схема для хранения эмбеддингов (pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE INDEX ON knowledge_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Гибридный индекс: вектор + полнотекстовый поиск
CREATE INDEX ON knowledge_chunks 
USING gin (to_tsvector('russian', content_ru));
```

**Post-MVP (при > 1M чанков):** Qdrant с именованными коллекциями по типу источника.

### 4.3 Метаданные-фильтры

Векторный поиск всегда сопровождается фильтрацией по метаданным:

```python
class VectorSearchFilter(BaseModel):
    source_types: list[str] | None = None      # Фильтр по типу источника
    legal_topics: list[str] | None = None      # Фильтр по правовой теме
    nice_classes: list[int] | None = None      # Фильтр по классам МКТУ
    effective_date_from: date | None = None    # Только актуальные источники
    min_confidence: float = 0.0                # Минимальный порог схожести
```

---

## 5. Стратегия ретривала

### 5.1 Типы запросов и конфигурации

| Тип запроса агента | Топик-фильтр | Top-K | Порог схожести | Источники приоритет |
|---|---|---|---|---|
| `absolute_grounds` | `absolute_grounds` | 10 | 0.70 | `gk_rf_part4`, `rospatent_guideline_tz` |
| `relative_grounds` | `relative_grounds` | 8 | 0.72 | `gk_rf_part4`, `rospatent_guideline_tz` |
| `classification` | `classification` | 12 | 0.65 | `mktu_alpha_index`, `rospatent_mktu_guide` |
| `conflict_analysis` | `conflict_analysis` | 6 | 0.75 | `gk_rf_part4`, `fips_refusal_cases` |
| `recommendation` | `recommendation` | 8 | 0.68 | Все источники |

### 5.2 Гибридный поиск (Hybrid Retrieval)

Для правовых запросов используется комбинация:

1. **Dense retrieval** — косинусное сходство векторов (80% вес).
2. **Sparse retrieval** — BM25 / полнотекстовый поиск по ключевым терминам (20% вес).

```python
# backend/app/rag/retrieval/hybrid_retriever.py
# Гибридный ретривер: комбинация семантического и полнотекстового поиска

class HybridRetriever:
    """Ретривер, комбинирующий векторный и BM25-поиск."""
    
    async def retrieve(
        self,
        query: str,
        search_filter: VectorSearchFilter,
        top_k: int = 10,
        dense_weight: float = 0.8,
        sparse_weight: float = 0.2,
    ) -> list[RetrievedChunk]:
        
        # Параллельный запуск обоих поисков
        dense_results, sparse_results = await asyncio.gather(
            self._dense_search(query, search_filter, top_k * 2),
            self._sparse_search(query, search_filter, top_k * 2),
        )
        
        # Reciprocal Rank Fusion для слияния результатов
        merged = reciprocal_rank_fusion(
            [dense_results, sparse_results],
            weights=[dense_weight, sparse_weight],
        )
        
        return merged[:top_k]
```

### 5.3 Переранжирование (Reranking)

После ретривала применяется cross-encoder для переранжирования топ-K результатов:

- **Модель:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (с поддержкой русского через multilingual версию).
- **Применение:** Только при `top_k > 5` (overhead нецелесообразен для малого K).

---

## 6. Отслеживание цитат (Citation Tracking)

Каждое правовое заключение агента ДОЛЖНО содержать массив `rag_citations`:

```python
class RAGCitation(BaseModel):
    source_code: str         # Идентификатор источника (напр.: "gk_rf_part4")
    source_name: str         # Отображаемое название
    chunk_id: UUID           # ID чанка в БД
    article_reference: str   # Ссылка на норму (напр.: «ст. 1483, п. 1 ГК РФ»)
    excerpt: str             # Цитата (первые 300 символов чанка)
    similarity_score: float  # Схожесть с запросом
    
class CitationTracker:
    """Трекер цитат для верификации правовых выводов агентов."""
    
    def verify_citations(
        self, 
        findings: list[LegalFindingSchema],
        retrieved_chunks: list[RetrievedChunk],
    ) -> CitationVerificationResult:
        """Проверяет, что каждый вывод подкреплён хотя бы одной цитатой."""
        ...
    
    def format_citations_for_prompt(
        self, 
        chunks: list[RetrievedChunk],
    ) -> str:
        """Форматирует чанки для включения в промпт."""
        ...
```

---

## 7. Оценка уверенности (Confidence Scoring)

```python
class ConfidenceScorer:
    """Вычисляет итоговую уверенность правового вывода."""
    
    def compute(
        self,
        llm_confidence: float,        # Уверенность от LLM (из structured output)
        max_citation_similarity: float,  # Макс. схожесть среди цитат
        citation_count: int,           # Количество цитат
        rag_coverage_score: float,     # Оценка покрытия темы RAG-базой
    ) -> float:
        
        # Взвешенная формула
        score = (
            llm_confidence * 0.40 +
            max_citation_similarity * 0.35 +
            min(citation_count / 5.0, 1.0) * 0.15 +
            rag_coverage_score * 0.10
        )
        return round(min(max(score, 0.0), 1.0), 3)
```

**Интерпретация:**
| Диапазон | Значение | Отображение юристу |
|---|---|---|
| 0.85–1.0 | Высокая уверенность | Зелёный |
| 0.65–0.85 | Средняя уверенность | Жёлтый |
| 0.45–0.65 | Низкая уверенность | Оранжевый |
| 0.0–0.45 | Очень низкая уверенность | Красный — требует особого внимания |

---

## 8. Fallback-режим (недостаточность источников)

Если RAG-ретривал не нашёл достаточно релевантных чанков (`coverage_score < 0.4` или `max_similarity < порог`):

```python
class RAGFallbackHandler:
    """Обработчик ситуации недостаточного покрытия базы знаний."""
    
    def handle(self, retrieval_result: RetrievalResult) -> FallbackResponse:
        if retrieval_result.coverage_score < 0.4:
            return FallbackResponse(
                mode=FallbackMode.INSUFFICIENT_COVERAGE,
                # Агент получает сигнал: отвечать нужно с явной оговоркой
                system_addition=(
                    "ВНИМАНИЕ: База знаний не содержит достаточно информации "
                    "по данному запросу. Ответ может быть неполным. "
                    "Обязательно укажи в поле 'confidence' значение ниже 0.5 "
                    "и в поле 'caveats' — что данная тема требует проверки юристом."
                ),
                rag_citations=[],
                confidence_cap=0.45,  # Максимальная уверенность в fallback
            )
```

**Правило:** В fallback-режиме:
1. Агент явно указывает `insufficient_rag_coverage: true` в выходной схеме.
2. `confidence_score` не может превышать `0.45`.
3. Юрист уведомляется о ненадёжности вывода.
4. Запись в `AuditLog` с флагом `rag_fallback: true`.

---

## 9. Управление версиями базы знаний

```
knowledge_base/
├── sources/
│   ├── gk_rf_part4/
│   │   ├── v1.0/
│   │   │   └── gk_rf_part4_2023.pdf
│   │   └── v1.1/           # Актуальная версия (после поправок)
│   │       └── gk_rf_part4_2025.pdf
│   ├── rospatent_order_8_2020/
│   │   └── v1.0/
│   │       └── order_8_2020.pdf
│   └── ...
├── ingestion_runs/
│   ├── 2026-01-15_full_rebuild.json   # Лог ингестии
│   └── 2026-03-01_incremental.json
└── README.md
```

**Политика обновления:**
- Изменения законодательства → новая версия `KnowledgeSource` + повторная ингестия только изменённых документов.
- Старые чанки помечаются `is_outdated=true`, не удаляются (для аудита).
- Перед активацией новой версии — регрессионные тесты (см. `testing-strategy.md`).

---

## 10. API внутреннего RAG-сервиса

Модуль `rag` предоставляет внутреннее API для агентов:

```python
# backend/app/rag/__init__.py

class RAGService:
    """Публичный API RAG-модуля."""
    
    async def retrieve_for_agent(
        self,
        query: str,
        agent_type: AgentType,
        nice_classes: list[int] | None = None,
        mark_type: MarkType | None = None,
    ) -> RAGContext:
        """Получение RAG-контекста для конкретного типа агента."""
        ...
    
    async def ingest_source(
        self,
        source_id: UUID,
        force_rebuild: bool = False,
    ) -> IngestionResult:
        """Запуск ингестии источника знаний."""
        ...
    
    async def get_coverage_report(
        self,
        topic: str,
    ) -> CoverageReport:
        """Оценка покрытия темы в базе знаний."""
        ...
```

---

## 11. Мониторинг качества RAG

| Метрика | Описание | Цель |
|---|---|---|
| `rag_retrieval_latency_p95` | P95 времени ретривала | < 500 мс |
| `rag_coverage_score_avg` | Среднее покрытие по запросам агентов | > 0.7 |
| `rag_fallback_rate` | Доля запросов, попавших в fallback | < 10% |
| `citation_verification_pass_rate` | Доля выводов с валидными цитатами | > 95% |
| `chunk_freshness_score` | Доля актуальных (не outdated) чанков | > 90% |
