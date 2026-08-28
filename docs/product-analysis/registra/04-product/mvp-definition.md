# MVP Definition: «Регистра»

**Дата:** 28 августа 2026 года  
**Phase:** 6 — Product  
**Basis:** repository/docs audit + Phase 3 research  
**Customer validation:** deferred

## Core hypothesis

`[Assumption]` Владелец простого уже используемого бренда заплатит 7 900 ₽ за explainable risk analysis и проверяемый filing package, если путь позволяет завершить дело самостоятельно, честно показывает ограничения и передаёт пограничный случай юристу без повторного intake.

## Реальный baseline

`[Data: repository documentation, 2026-08-28]` Уже реализованы: шесть клиентских этапов; extraction ЕГРЮЛ/ЕГРИП/OCR; подтверждение данных и provenance; guided МКТУ; class-first registry analysis; fee calculation; DOCX/ZIP для простого кейса; admin/lawyer assignment; notification response draft; persistent background worker; access controls and deletion; production compose. `[Data]` В `backend/tests` найдено 91 определения тестов; это inventory, не результат прогона.

## v1.0 — must have for controlled paid pilot

1. **Narrow eligibility gate:** только word/combined simple case, один заявитель, 1–3 класса, no priority/representative/complex red flags.
2. **P0 legal acceptance:** юрист подписывает page-by-page checklist для организации, ИП и физлица.
3. **Real extraction eval:** обезличенный корпус разных поколений выписок и плохих сканов; unsafe fallback.
4. **Personal-data launch package:** operator basis, privacy/consents, retention/deletion, processor terms, RKN decision, Russian storage/backup.
5. **Registry limitation disclosure:** timestamp, coverage and incomplete-state; no «risk absent» on timeout.
6. **Paid concierge controls:** payment/offer/refund scope; manual lawyer review for every first cohort case, even if client buys self-service.
7. **Product analytics:** event funnel, case complexity, review minutes, errors, rework and source.
8. **Production rehearsal:** PostgreSQL, worker, HTTPS, encrypted off-host backup, restore drill, monitoring and incident contact.

## v1.1 — should have after first 20 paid cases

- Preview of application with field-source highlights.
- Unified blocker navigation across fees/package/response.
- Human-review checkout and SLA.
- Referral/partner attribution.
- Response triage and transparent scenario pricing.
- Accessibility/mobile/keyboard test.

## Explicitly out of v1.0

Automatic electronic filing/signature; multiple applicants; international/priority/collective/nontraditional cases; full image→registry search; guaranteed legal outcome; bank/marketplace integrations; full Gardium-like B2B suite; Kubernetes/multi-region infrastructure.

## Success criteria

All thresholds — `[Assumption]` until pilot.

| Dimension | Pilot criterion |
|---|---|
| Demand | ≥20 paid cases, not founder friends only |
| Completion | ≥60% qualified starts reach approved package |
| Quality | 100% first cohort reviewed; no critical document error |
| Safety | 0 unauthorized disclosures; deletion/restore drill passes |
| Operations | median human intervention recorded; target ≤45 min/simple case |
| Economics | one channel CAC ≤2 300 ₽; positive contribution after actual support |
| Trust | ≥50% of payers cite evidence/human fallback as decision factor |

## Data Gaps

Test suite result on current dirty branch, real document accuracy, legal acceptance, customer completion, review time, production SLA and payment flow.

## Red Flags

- `[Risk]` Product must not accept paid external passport/document cases before P0 data governance and backup are approved.

## Yellow Flags

- `[Risk]` Advanced implemented functionality can distract from qualifying a narrow safe pilot.

