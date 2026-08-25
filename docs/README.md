# Документация «Регистра»

**Актуализировано:** 26 августа 2026 года.

Документация разделена на актуальные рабочие документы и архив. Начинайте с
[`current-state.md`](current-state.md): это единая точка правды о реализованных
функциях и ограничениях. Если текст расходится с кодом или тестами, приоритет
имеют код и тесты.

## Основные документы

| Задача | Документ |
|---|---|
| Понять, что работает сейчас | [`current-state.md`](current-state.md) |
| Увидеть следующие задачи и ограничения | [`roadmap.md`](roadmap.md) |
| Вести конкретные продуктовые задачи | [`backlog.md`](backlog.md) |
| Понять продукт, аудиторию и продвижение | [`business-go-to-market.md`](business-go-to-market.md) |
| Оценить экономику, инфраструктуру и SLA | [`operating-economics-and-sla.md`](operating-economics-and-sla.md) |
| Запустить локальный стенд | [`demo-deployment.md`](demo-deployment.md) |
| Развернуть production | [`production-architecture.md`](production-architecture.md) |
| Запустить проверки | [`testing.md`](testing.md) |

## Технический справочник

| Область | Документы |
|---|---|
| Архитектура и данные | [`architecture.md`](architecture.md), [`domain-model.md`](domain-model.md), [`state-machine.md`](state-machine.md) |
| API | [`api-contracts.md`](api-contracts.md) |
| Входящие и исходящие документы | [`document-extraction.md`](document-extraction.md), [`document-pipeline.md`](document-pipeline.md) |
| AI, RAG и право | [`rag-and-legal-safety.md`](rag-and-legal-safety.md), [`legal-coverage.md`](legal-coverage.md) |
| Ответы Роспатенту | [`office-action-responses.md`](office-action-responses.md) |
| Внешние сервисы | [`integrations.md`](integrations.md), [`rospatent-open-api.md`](rospatent-open-api.md) |
| Безопасность | [`security.md`](security.md) |

## Архив

Исторические аудиты, отчёты о завершённых изменениях и дореализационные
спецификации перенесены в [`archive/`](archive/README.md). Они сохранены для
контекста, но не должны использоваться как описание текущего продукта.
