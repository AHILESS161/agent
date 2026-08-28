# Проверяемая карта уверенности

**Срез:** 28 августа 2026 года  
**Customer evidence:** `[Data] 0 интервью / 0 продаж`  
**Правило corroboration:** несколько публикаций одного ведомства или компании считаются одним source family.

| Тезис | Тип | Источник | Tier | Независимых families | Возраст | Уверенность | Ограничение / проверка |
|---|---|---|---|---:|---|---|---|
| Физлица могут владеть ТЗ без ИП | `[Data]` | [Роспатент](https://rospatent.gov.ru/ru/news/30-10-2025-kak-zaregistrirovat-svoy-brend-poshagovaya-instrukciya-ot-rospatenta), действующая норма | T1 | 1 | <18 мес. | Высокая | legal monitoring |
| Заявки самозанятых росли быстрее общего рынка в 2025 | `[Data/Estimate]` | [годовой отчёт](https://rospatent.gov.ru/content/uploadfiles/docs/032026/RP-Annual-2025-SHORT-1803.pdf) | T1 | 1 | <18 мес. | Высокая | не обобщать на весь B2C без сопоставимой выгрузки |
| B2C transaction flow 74,5–86,0 тыс. | `[Estimate]` | [Роспатент 2025](https://rospatent.gov.ru/ru/news/09-02-2026-chislo-zayavok-na-tovarnye-znaki-dostiglo-rekorda) + отчёт, один family | T1 | 1 | <18 мес. | Средняя | знаменатель 55% неоднозначен; запросить выгрузку |
| B2C TAM 588–679 млн ₽ | `[Estimate]` | предыдущий поток × `[Assumption]` 7 900 ₽ | T1 + founder | 1 | current | Средняя | transaction TAM, не buyers/revenue |
| B2C SAM 134–155 млн ₽ | `[Estimate]` | TAM × `[Assumption]` 65% × 35% | model | 0 | current | Низкая | разметить 100 дел + WTP test |
| SOM goal 120–240 дел | `[Assumption]` | founder capacity model | model | 0 | current | Низкая | не называть достижимым до sales |
| Цена 7 900 ₽ конвертирует | `[Assumption]` | founder price; competitor anchors | T2 + founder | 0 independent demand | current | Низкая | checkout с полным чеком |
| Полный минимум 42 900 ₽ | `[Estimate]` | [пошлины Роспатента](https://rospatent.gov.ru/ru/stateservices/gosudarstvennaya-registraciya-tovarnogo-znaka-znaka-obsluzhivaniya-kollektivnogo-znaka-i-vydacha-svidetelstv-na-tovarnyy-znak-znak-obsluzhivaniya-kollektivnyy-znak-ih-dublikatov) + 7 900 ₽ | T1 + founder | 1 | accessed 2026-08-28 | Высокая | дополнительные классы увеличивают чек |
| Private label — beachhead | `[Opinion]` | secondary pains, channels, geography | T2/T3 | несколько, heterogeneous | mixed | Средняя | 15 interviews + segment test |
| Дорогая ошибка — top pain | `[Estimate from secondary research]` | публичные кейсы/отзывы | T3 | несколько площадок | mixed | Средняя | self-selection; интервью |
| Evidence pack имеет WTP | `[Assumption]` | синтез pain→solution | — | 0 | current | Низкая | A/B proposition + payment |
| Human review повысит trust/conversion | `[Assumption]` | general legal-AI survey + hybrid supply | T2 | 2 indirect | <18 мес. | Средняя | trademark-specific A/B |
| Basic list/pre-check/draft коммодитизируется | `[Opinion]` | Linkmark, xyma, Брендоскоп, state tools | T1/T2 | 4 | current | Высокая | не распространять на legal analysis |
| Evidence/workflow способен стать moat | `[Assumption]` | strategic synthesis | — | 0 | current | Средняя | measure reuse, outcomes, switching |
| CAC ceiling 2,0–2,3 тыс. ₽ | `[Assumption]` | contribution-margin reserve model | model | 0 | current | Низкая | cohort GP after support/refunds |
| Partner channel уложится в CAC | `[Assumption]` | 15–20% rev-share proxy | T2 offers | 1 market pattern | current | Низкая | 50 outreach / paid cohorts |
| B2B 50k рационален при 10–20+ делах | `[Estimate based on Assumptions]` | cost per matter model | model | 0 | current | Низкая | 8–15 interviews + paid pilots |
| B2B TAM 153–632 млн ₽ ARR | `[Estimate based on Assumptions]` | firm-equivalent model | T1 volume + model | 1 | current | Низкая | firm census/volume sample |
| Ответ на запрос — лучший first upsell | `[Opinion]` | customer pain + competitor pricing | T2/T3 | несколько | mixed | Средняя | concierge pilot |
| Федеральный launch лучше city-first | `[Opinion]` | distributed applications/digital workflow | T1/T2 | 2 | mixed | Средняя | geo cohorts |
| Raw passport docs in foreign LLM — launch risk | `[Risk/Data]` | 152-ФЗ и regulatory analysis | T1 | 1 legal framework | current | Высокая | DPIA + counsel review |

## Data Gaps

`[Data gap]` WTP; simple-case share; accuracy against attorney; human-review cost/SLA; free→paid conversion; CAC; official-query frequency; B2B workflow and WTP.

## Decision rule

`[Opinion]` Красного market-size флага нет. `[Data]` Есть четыре неразрешённых launch conditions: customer evidence, contribution economics, AI/legal quality и personal-data safety. `[Opinion]` Продолжать validation, сохраняя B2C-first; полный B2B suite отложить.

## Red Flags

- `[Data]` Ни один customer/price/channel thesis не подтверждён интервью или оплатой.
- `[Risk]` Personal-data architecture может блокировать production независимо от market attractiveness.

## Yellow Flags

- `[Data quality]` B2C flow основан на одном source family с разными знаменателями.
- `[Assumption]` SOM, CAC, WTP, simple share, review cost и B2B volume остаются моделью.
- `[Staleness]` Данные 2024 года используются только как исторический ряд и явно помечены в market analysis.
