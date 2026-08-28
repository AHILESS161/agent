# Financial Projections: «Регистра»

**Дата:** 28 августа 2026 года  
**Financial Model Stage:** A — Assumption-Based | Это сценарии для решений, не прогнозы.

## Year 1 scenario drivers

All three scenarios use one formula and the same price/cost basis. One-time launch reserve is shown separately and never mixed into operating result.

| Driver | Conservative | Base | Optimistic |
|---|---:|---:|---:|
| B2C paid cases | 120 | 240 | 360 |
| Core package price | 7 900 ₽ | 7 900 ₽ | 7 900 ₽ |
| Human-review attach / incremental price | 15% / 6 000 ₽ | 25% / 6 000 ₽ | 35% / 6 000 ₽ |
| Formal-notification rate / paid attach among eligible | 20% / 25% | 25% / 40% | 30% / 50% |
| Effective response attach / average price | 5% / 12 000 ₽ | 10% / 12 000 ₽ | 15% / 12 000 ₽ |
| B2B revenue | 0 ₽ | 200 000 ₽ | 1 080 000 ₽ |
| Base delivery / review / response delivery | 1 000 / 3 500 / 7 000 ₽ | same | same |
| B2B delivery | 20% of B2B revenue | same | same |
| CAC / tax | 2 000 ₽ per B2C / 6% revenue | same | same |
| Recurring fixed cash cost | 500 000 ₽ | 500 000 ₽ | 500 000 ₽ |
| One-time launch reserve | 270 000 ₽ | 270 000 ₽ | 270 000 ₽ |
| Founder shadow salaries | 4 800 000 ₽ | 4 800 000 ₽ | 4 800 000 ₽ |

## Year 1 scenario results

| Scenario | Revenue | Recurring cash cost | Operating cash result before founders | After one-time launch | Economic result after launch + founder shadow salaries |
|---|---:|---:|---:|---:|---:|
| Conservative | `[A]` 1 128 000 ₽ | `[A]` 1 032 680 ₽ | `[E]` +95 320 ₽ | `[E]` −174 680 ₽ | `[E]` −4 974 680 ₽ |
| Base | `[A]` 2 744 000 ₽ | `[A]` 1 802 640 ₽ | `[E]` +941 360 ₽ | `[E]` +671 360 ₽ | `[E]` −4 128 640 ₽ |
| Optimistic | `[A]` 5 328 000 ₽ | `[A]` 2 934 680 ₽ | `[E]` +2 393 320 ₽ | `[E]` +2 123 320 ₽ | `[E]` −2 676 680 ₽ |

Formulas: revenue = core + review + response + B2B; recurring cash cost = base delivery + review delivery + response delivery + 20% B2B delivery + 500k fixed + CAC + 6% tax. All drivers are `[Assumption — unvalidated]`.

## Base cash-flow interpretation

`[Estimate]` Monthly revenue exceeds modeled recurring fixed cash cost early, but cumulative cash may remain negative during setup/acquisition. A prudent launch reserve is not the same as total funding need.

- `[Assumption]` Minimum cash reserve without founder salaries: **600–900 тыс. ₽**, covering one-time readiness work plus several months of operating uncertainty.
- `[Assumption]` Nine-month runway including 400 тыс. ₽ monthly founder salaries: roughly **4,0–4,8 млн ₽**, before aggressive acquisition.
- `[Opinion]` Raising institutional capital before paid/quality proof would likely produce weak terms; a controlled pilot can create materially better evidence at modest cash cost.

## Year 1–3 base path

| Year | Revenue | Direct delivery/infra estimate | Acquisition/fixed/team/tax estimate | Cash operating result | Confidence |
|---:|---:|---:|---:|---:|---|
| 1 | 2,744m ₽ | 0,838m ₽ incl. core fixed infra | 0,965m ₽ | +0,941m ₽ before founders and one-time launch | Low |
| 2 | 11,242m ₽ | 3,476m ₽ | 4,214m ₽ incl. first ops hire | +3,552m ₽ before founders | Very Low |
| 3 | 35,550m ₽ | 11,115m ₽ | 13,413m ₽ incl. team expansion | +11,022m ₽ before founders | Very Low |

`[Assumption]` Year 2 includes one operations/support hire; Year 3 includes a small operating/legal team. `[Data gap]` Headcount plan is not designed deeply enough to treat these results as reliable.

## Top-five sensitivity assumptions

| Assumption | Current | If 50% worse | Consequence | Validation |
|---|---|---|---|---|
| B2C paid volume | 240 Y1 | 120 | revenue near conservative case | interviews + paid cohort |
| Blended CAC | 2 000 ₽ | 3 000 ₽ | −240k ₽ Y1 contribution | channel cohorts |
| Human intervention | ≤45 min simple | 90 min | capacity/margin roughly halves for review-heavy work | time tracking |
| Paid eligibility | implicit in volume | half of leads qualify | acquisition funnel doubles | routing analytics |
| B2B adoption | 3 pilots ending Y1 | 1 or 0 | little Y1 impact, large Y2/3 downside | design-partner pilots |

## Funding recommendation

`[Opinion]` До 20 платных дел — bootstrap/very small founder reserve. После 20 дел и quality evidence — decide whether 600–900k ₽ working capital is enough. Investor fundraising becomes more defensible after 100+ cases, one repeatable channel and measured lawyer disagreement/manual cost.

## Data Gaps

Payment timing, refunds, taxes, salary expectations, legal capacity, external data pricing, B2B churn and lifecycle attach rates.

## Red Flags

- `[Risk]` Year 2–3 apparent profitability depends on growth that has zero customer evidence today.

## Yellow Flags

- `[Risk]` Optimistic scenario is not investor-grade forecast and must be labelled scenario in Figma.
