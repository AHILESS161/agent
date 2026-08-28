# Validation Playbook: «Регистра»

**Дата:** 28 августа 2026 года  
**Phase:** 8 — Validation  
**Customer interviews:** deferred; therefore Experiment #1

## Ordered experiments

| # | Experiment | Assumption | Method | Pass | Fail | Time / cash |
|---:|---|---|---|---|---|---|
| 1 | B2C problem interviews | pain/beachhead real | 5 interviews with active private-label owners | ≥4/5 unprompted pain; ≥2 behavior signals | ≤3 confirm or 0 behavior | 1 week / 0–15k ₽ |
| 2 | Paid concierge pilot | WTP 7 900 ₽ | real landing + manual lawyer-backed package | ≥5 non-friend payments from 20 qualified conversations | <3 payments or dominant fee objection | 2–3 weeks / low |
| 3 | Blind quality benchmark | product output useful/safe | 20 historical anonymized simple cases, system vs lawyer | 0 critical filing errors; ≥90% material facts accepted; disagreements classified | any repeat critical error | 1–2 weeks / lawyer time |
| 4 | Full funnel cohort | free map converts | 300 qualified completions | ≥3% paid, CAC ≤2 300 ₽ | <1% paid after message iteration | 4–8 weeks |
| 5 | Human-review A/B | review adds trust/WTP | offer self-service vs review tier | ≥20% choose review or conversion rises materially | no preference at sustainable price | 20+ payments |
| 6 | Partner channel | borrowed trust works | 50 targeted outreach | 5 active partners; ≥5 paid intros | <2 active or CAC > ceiling | 4–6 weeks |
| 7 | Response concierge | lifecycle revenue | serve first real notifications manually | ≥30% eligible attach; positive margin | support burden exceeds price | event-driven |
| 8 | B2B design partner | repeated workflow ROI | 2 firms, historical/live anonymized cases | ≥30% time saved and paid continuation | no repeated use/payment | 4–6 weeks |
| 9 | Production reliability | several applications safely in flight | 5 concurrent case jobs; inject provider timeout and worker restart; verify retry, idempotency, restore and alerts | 5/5 finish; no lost/duplicate case; restart recovery ≤15 min; alert received ≤5 min | any lost/duplicated case or silent failure | 1 day + remediation |

Все thresholds — `[Assumption]`, выбранные как decision rules.

## Sequence rule

Do not buy broad traffic or build direct filing before Experiments 1–3. Do not build full B2B portfolio before Experiment 8 passes.

## Data Gaps

Recruitment access, qualified denominator, legal benchmark definition and acceptable error taxonomy.

## Sequence Rule

Paid fulfillment with external personal documents cannot begin until the privacy/legal readiness gate and Experiment 9 production-reliability gate both pass. Before that point Experiment 2 may collect interviews or payment intent only, without document upload.

## Red Flags

- `[Risk]` Skipping interviews again would turn product analytics into expensive problem discovery.

## Yellow Flags

- `[Risk]` Five interviews are directional, not statistically representative.
