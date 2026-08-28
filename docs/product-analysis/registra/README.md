# Полный анализ продукта «Регистра»

**Дата:** 28 августа 2026 года  
**Вердикт:** Conditional proceed — 6,5/10  
**Evidence stage:** pre-revenue; customer discovery deferred

## Executive summary

«Регистра» — сервис проверяемой подготовки заявки на товарный знак для владельцев уже используемых товарных/private-label брендов. Продукт помогает оценить риск до оплаты пошлин, сформировать корректный scope МКТУ и получить редактируемый DOCX/ZIP с прозрачным происхождением данных; пограничные дела передаются юристу без повторного intake. Технически проект уже является развитым локальным MVP, но рыночная сторона остаётся гипотезой: нет интервью, оплат, CAC и подтверждённой willingness-to-pay.

## Key findings

- `[Estimate]` B2C transaction TAM при 7 900 ₽: 588–679m ₽/год.
- `[Data]` Быстрый рост напрямую подтверждён для заявок самозанятых; весь B2C range имеет medium confidence.
- `[Data]` Минимальные пошлины simple one-class case: 35 000 ₽; полный минимум с сервисом: 42 900 ₽.
- `[Opinion]` Basic search/pre-check/filing коммодитизируются; wedge — evidence, documents, routing and lifecycle.
- `[Data: repository audit]` Уже работают end-to-end local flow, extraction, МКТУ, analysis, fees, DOCX/ZIP, professional access, response draft and production worker.
- `[Estimate based on Assumptions]` Base Year 1: 240 B2C cases, 2,744m ₽ revenue, +941k ₽ operating cash before founder salaries and one-time launch; −4,129m ₽ after the 270k ₽ launch reserve and 4,8m ₽ founder shadow salaries.

Ключевые основания: [TAM/SAM/SOM](01-discovery/market-analysis.md), [beachhead и боли](01-discovery/target-audience.md), [ценовой ландшафт](01-discovery/competitor-landscape.md), [проверка фактов](01-discovery/verification-report.md).

## Positioning

> Проверьте риск до оплаты пошлин, получите документы с понятными основаниями и подключите юриста только там, где автоматизации недостаточно.

## Top risks and mitigation

1. **No paid demand:** interviews → paid concierge → funnel cohort.
2. **Legal/AI error:** narrow eligibility → blind benchmark → human review.
3. **PII/privacy:** minimization → Russian storage → legal package → backup/restore drill.

## What we know vs. guess

**Stronger evidence:** regulation, filing volume, fees, competitor supply, implemented technical capabilities.  
**Weak evidence:** pain priority, price conversion, simple-case share, CAC, human labor, response attach and B2B subscription.

## Data Gaps

Пять интервью с точным beachhead; первые реальные оплаты; lawful 20-case benchmark corpus; подтверждённые review minutes и CAC; privacy/legal sign-off; concurrent-job retry/recovery evidence; B2B retention and ARPA.

## Anti-Patterns Detected

- **Building in stealth too long:** advanced product, zero interviews/sales.
- **Boiling the ocean:** B2C, B2B, filing, responses and portfolio in one roadmap.
- **Vanity milestone risk:** production deployment can look like success without paid completion.
- **Ignoring economic labor:** cash margin appears positive while founder shadow-cost result is negative.

## Document map

### Figma reports

[Инвесторский отчёт — 12 слайдов](https://www.figma.com/slides/KxBcKQXbC2kX6QrNLyaXhe) · [Клиентский отчёт — 8 слайдов](https://www.figma.com/slides/fGIvLHDH6xkr5Y11cmLl7c)

### PowerPoint presentations

[Инвесторская презентация — PPTX](presentations/registra-investor.pptx) · [Клиентская презентация — PPTX](presentations/registra-client.pptx)

PowerPoint-версии являются рекомендуемыми для показа: они перевёрстаны с нуля, проверены через PNG contact sheets и содержат Fade/Push/Wipe transitions на каждом слайде.

### Discovery

[Market](01-discovery/market-analysis.md) · [Competitors](01-discovery/competitor-landscape.md) · [Audience](01-discovery/target-audience.md) · [Trends](01-discovery/industry-trends.md) · [Confidence](01-discovery/confidence-dashboard.md) · [Verification](01-discovery/verification-report.md)

### Strategy

[Lean Canvas](02-strategy/lean-canvas.md) · [Value Proposition](02-strategy/value-proposition.md) · [Business Model](02-strategy/business-model.md) · [Positioning](02-strategy/positioning.md) · [GTM](02-strategy/go-to-market.md)

### Brand

[Mission/Vision/Values](03-brand/mission-vision-values.md) · [Tone of Voice](03-brand/tone-of-voice.md) · [Brand Personality](03-brand/brand-personality.md)

### Product

[MVP](04-product/mvp-definition.md) · [Priorities](04-product/feature-prioritization.md) · [Journey](04-product/user-journey.md)

### Financial

[Revenue](05-financial/revenue-model.md) · [Costs](05-financial/cost-structure.md) · [Projections](05-financial/projections.md)

### Validation

[Playbook](06-validation/validation-playbook.md) · [Risks](06-validation/risk-analysis.md) · [Assumptions](06-validation/assumptions-tracker.md) · [Top Experiments](06-validation/experiment-design.md) · [Kill Criteria](06-validation/kill-criteria.md) · [Scorecard](06-validation/scorecard.md)

## Red Flags

- `[Data]` Customer interviews and sales are both zero.

## Yellow Flags

- `[Risk]` External investor/client materials must not present Stage A scenarios as forecasts.
