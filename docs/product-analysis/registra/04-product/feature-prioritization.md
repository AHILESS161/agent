# Feature Prioritization: «Регистра»

**Дата:** 28 августа 2026 года  
**Method:** MoSCoW + dependency order  
**Confidence:** Medium for launch safety; Low for demand impact

## Priorities

| Priority | Capability | Status | Effort | Dependency / rationale |
|---|---|---|---|---|
| Must | Narrow eligibility/routing gate | partial | M | protects quality/margin |
| Must | Legal acceptance of 3 simple DOCX scenarios | ready for review | S | blocks paid promise |
| Must | Real EGRUL/EGRIP extraction eval | harness ready | M | blocks safe prefill |
| Must | Privacy/retention/processor/RKN package | technical baseline only | M | regulatory blocker |
| Must | Off-host encrypted backup + restore drill | planned | M | required for real documents |
| Must | Production monitoring/alerts/runbook | partial | M | pilot operations |
| Must | Payment + offer + refund boundaries | not evidenced | M | paid pilot dependency |
| Must | Funnel/quality/manual-time analytics | not evidenced | M | validates hypothesis |
| Should | Human review tier and assignment SLA | assignment exists | M | trust/WTP test |
| Should | Application preview with provenance | backend provenance exists | M | catches error before ZIP |
| Should | Unified blocker navigation | partial | S | completion |
| Should | Response triage product | draft flow exists | M | lifecycle revenue |
| Should | Partner/referral attribution | absent | S–M | GTM measurement |
| Could | Direct electronic filing/signature | absent | XL | external/legal dependency |
| Could | Full visual reverse search | absent | XL | data/index dependency |
| Could | B2B templates/bulk portfolio | partial professional cabinet | L–XL | needs design partners |
| Won't v1 | Multiple applicants/priority/international | partial manifest only | XL | complex legal scope |
| Won't v1 | Kubernetes/multi-region | absent | XL | no load evidence |

## Recommended build order

1. Freeze pilot eligibility and refusal/escalation rules.
2. Complete legal DOCX acceptance and real extraction evaluation.
3. Finalize privacy governance, backup restore and monitoring.
4. Add payment/offer plus analytics and case-cost instrumentation.
5. Run 5 moderated free cases, then 5 paid concierge, then 20 paid cohort.
6. Build preview/human-review improvements only from observed drop-offs.
7. Add response product when real notifications arrive.
8. Start B2B product work only with 2 design partners.

## Why RICE is not used yet

`[Data]` Reach and impact have no production cohorts. A numeric RICE score would create false precision. After 20 paid cases, use observed affected-user counts and completion lift.

## Data Gaps

Current test-run result, exact implementation state of payments/analytics, owner estimates, review capacity, vendor lead times and external API terms.

## Red Flags

- `[Risk]` Direct filing before legal/technical channel design materially expands liability.

## Yellow Flags

- `[Risk]` Existing response/B2B work may be ahead of validated B2C activation.

