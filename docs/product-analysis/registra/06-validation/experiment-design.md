# Top-3 Experiment Design

**Дата:** 28 августа 2026 года  
**Phase:** 8 — Validation

## Experiment 1 — Problem interviews

**Hypothesis:** `[Assumption]` 4/5 active brand owners describe risk before fees/packaging unprompted; 2+ show paid/search/workaround behavior.

**Recruit:** own/private-label product brand; already selling/preparing launch; considered filing in last 12 months; exclude general self-employed without own brand.

**Protocol (25–30 min):** last time they considered protection → exact actions → fees/classes/search → workaround/spend → outcome. Do not show «Регистра» until the interview ends.

**Outreach template:**

> Здравствуйте! Исследую, как владельцы собственных товарных брендов проверяют название и готовятся к регистрации. Ничего не продаю — хочу разобраться в последнем реальном опыте. Можно попросить 25 минут? Особенно полезно, если вы уже выбирали классы, консультировались или подавали заявку.

**Pass:** 4/5 pain confirmation, ≥2 behavior signals, similar language.  
**Fail:** ≤3/5, no behavior, or primary pain differs.

## Experiment 2 — Paid concierge

**Hypothesis:** `[Assumption]` qualified customer pays 7 900 ₽ after seeing full minimum budget and sample result.

**Method:** one landing; clear 35 000 ₽ minimum fees; sample evidence report; qualification form; payment; founders manually guarantee process quality, not registration outcome. Lawyer reviews every case internally.

**Landing outline:**

1. «Проверьте риск до оплаты пошлин».
2. Three outputs: conflicts with reasons, МКТУ scope, DOCX/ZIP.
3. Example result with source/date.
4. 7 900 ₽ service + government fees separately.
5. Complex case → explicit lawyer route.
6. CTA: «Проверить, подходит ли мой случай».

**Measure:** qualified conversations; checkout starts; payments; objections; refund/rework; minutes/case; source.  
**Pass:** ≥5 payments from first 20 qualified non-friend prospects.  
**Fail:** <3 payments or >50% cite service price after understanding value.

## Experiment 3 — Blind quality benchmark

**Hypothesis:** `[Assumption]` For eligible simple cases the system produces no critical filing error and captures ≥90% material facts accepted by lawyer.

**Dataset:** 20 anonymized historical cases, balanced organization/IP/individual, 1–3 classes, word/combined marks, clean and noisy source docs.

**Blind process:** freeze system version → generate output → lawyer reviews without seeing system confidence → label critical/major/minor/style disagreement → second adjudicator resolves critical disputes where possible.

**Metrics:** field exactness; missing/incorrect material fact; МКТУ agreement; conflict recall/precision proxy; critical document errors; minutes to correct.

**Pass:** 0 critical filing errors, ≥90% material facts accepted, median correction ≤15 min.  
**Fail:** repeated critical pattern or inability to reproduce source chain.

## Data Gaps

Recruitment pool, historical-case rights/consent, adjudication availability and exact quality taxonomy.

## Red Flags

- Benchmark must not use the same synthetic fixtures that shaped the implementation.

## Yellow Flags

- Twenty cases detect major patterns but do not establish population-level accuracy.

