# Документация «Регистра»

**Актуализировано:** 19 августа 2026 года.

Начинать знакомство с проектом следует с [`current-state.md`](current-state.md):
это единая точка правды о реализованных функциях, ограничениях и маршрутах
пользователей. Если проектная спецификация расходится с текущим состоянием,
приоритет имеет код, тесты и `current-state.md`.

## Продукт и пользовательские пути

| Документ | Назначение |
|---|---|
| [`current-state.md`](current-state.md) | фактическое состояние продукта на сегодня |
| [`target-audience-and-positioning.md`](target-audience-and-positioning.md) | основная аудитория и продуктовая модель |
| [`business-go-to-market.md`](business-go-to-market.md) | коммерческий потенциал, тарифы, продвижение и экономика |
| [`operating-economics-and-sla.md`](operating-economics-and-sla.md) | нагрузочные сценарии, команда, стоимость LLM, серверы и SLA/SLO |
| [`marketing-strategy.md`](marketing-strategy.md) | ICP, позиционирование, каналы, бюджет, KPI и план на 90 дней |
| [`investor-pitch.html`](investor-pitch.html) | интерактивная инвестиционная презентация, печать в PDF |
| [`investor-pitch.pdf`](investor-pitch.pdf) | готовая инвестиционная презентация 16:9 без обрезания слайдов |
| [`ux-audit-2026-08.md`](ux-audit-2026-08.md) | изменения клиентского и профессионального интерфейсов |
| [`office-action-responses.md`](office-action-responses.md) | уведомления Роспатента, доказательства и безопасный LLM-черновик ответа |
| [`professional-client-parity.md`](professional-client-parity.md) | паритет возможностей клиента и юриста, оставшиеся разрывы и приоритеты |
| [`release-notes-2026-08-17.md`](release-notes-2026-08-17.md) | реализация замечаний по итогам клиентского тестирования |
| [`roadmap.md`](roadmap.md) | выполненное, оставшиеся задачи и внешние зависимости |
| [`frontend-audit.md`](frontend-audit.md) | переход от mock-интерфейса к реальному API |

## Реализация

| Документ | Назначение |
|---|---|
| [`architecture.md`](architecture.md) | компоненты и фактические потоки данных |
| [`api-contracts.md`](api-contracts.md) | HTTP API, клиентский черновик и пошлины |
| [`domain-model.md`](domain-model.md) | сущности и связи; часть разделов остаётся целевой моделью |
| [`state-machine.md`](state-machine.md) | статусы и переходы заявки |
| [`document-extraction.md`](document-extraction.md) | PDF/DOCX/TXT/изображения, regex и OCR |
| [`document-pipeline.md`](document-pipeline.md) | предпросмотр, рабочий DOCX и утверждённые версии |
| [`agent-graph.md`](agent-graph.md) | целевой агентный граф и реализованные части |

## AI, RAG и правовой анализ

| Документ | Назначение |
|---|---|
| [`rag-and-legal-safety.md`](rag-and-legal-safety.md) | фактические границы AI и юридические гарантии |
| [`rag-design.md`](rag-design.md) | целевая архитектура RAG и текущий BM25-контур |
| [`prompt-registry.md`](prompt-registry.md) | версии промптов и правила безопасного анализа |
| [`legal-coverage.md`](legal-coverage.md) | покрытие правовых оснований и известные пробелы |
| [`rospatent-open-api.md`](rospatent-open-api.md) | официальный и ограниченный публичный поиск |
| [`integrations.md`](integrations.md) | GigaChat, реестры и отсутствующие внешние каналы |

## Эксплуатация и качество

| Документ | Назначение |
|---|---|
| [`demo-deployment.md`](demo-deployment.md) | локальный запуск и временный доступ извне |
| [`server-production-plan.md`](server-production-plan.md) | отложенный production-план |
| [`production-architecture.md`](production-architecture.md) | готовый production-контур, деплой, бэкапы и путь масштабирования |
| [`security.md`](security.md) | модель доступа, секреты и ограничения демо-режима |
| [`testing.md`](testing.md) | актуальные команды и текущее покрытие |
| [`testing-strategy.md`](testing-strategy.md) | целевая стратегия тестирования |
| [`repository-audit.md`](repository-audit.md) | исторический аудит и этапы восстановления |
