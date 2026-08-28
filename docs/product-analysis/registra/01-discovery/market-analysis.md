# Рыночный анализ «Регистры»

**Срез данных:** 28 августа 2026 года  
**География:** Россия  
**Интервью / продажи:** `[Data] 0 / 0`  
**Уверенность:** средняя для transaction market; низкая для платного спроса

## Вердикт

`[Data, Tier 1]` С 29 июня 2023 года физические лица могут владеть товарными знаками без ИП. `[Data, Tier 1, Stale >18 months]` В 2024 году физлица, самозанятые и ИП дали 54% российских заявок. `[Data, Tier 1]` Заявки самозанятых выросли с 21,4 тыс. в 2024 году до 25,2 тыс. в 2025 году, или на 17,8%. `[Data, Tier 1]` Общий поток российских заявок в 2025 году снизился на 1,5%.

`[Opinion, medium confidence]` Появился новый B2C-слой внутри зрелого рынка; быстрый рост напрямую доказан для самозанятых, но пока не для всей совокупности B2C. `[Estimate]` Корректный знаменатель — 74,5–86,0 тыс. B2C-транзакций в год, а не 16,2 млн самозанятых. Публикации Роспатента считаются одним source family, а не независимыми подтверждениями.

`[Opinion]` Проект стоит продолжать, но исследование не доказывает willingness-to-pay, доверие или repeatable acquisition.

## Reconciliation исходных данных

| Год | Категория | Значение | Единица | Источник / статус | Использование |
|---|---|---:|---|---|---|
| 2024 | Российские заявки | 137 436 | заявки | `[Data, Tier 1, Stale]` [Роспатент](https://rospatent.gov.ru/ru/news/18-02-2025-v-2024-godu-brendingovaya-aktivnost-rossiyskogo-biznesa-vyrosla-na-12) | база проверки |
| 2024 | Физлица + самозанятые + ИП | 54% | доля российских заявок | `[Data, Tier 1, Stale]` тот же source family | нижний proxy |
| 2025 | Российские заявки | 135 363 | заявки | `[Data, Tier 1]` [годовой отчёт](https://rospatent.gov.ru/content/uploadfiles/docs/032026/RP-Annual-2025-SHORT-1803.pdf) | база TAM |
| 2025 | Все заявки | 156 365 | заявки | `[Data, Tier 1]` тот же отчёт | верхний знаменатель |
| 2025 | Доля физлиц | 55% | доля с неоднозначным знаменателем | `[Data, Tier 1]` [Роспатент](https://rospatent.gov.ru/ru/news/09-02-2026-chislo-zayavok-na-tovarnye-znaki-dostiglo-rekorda) | диапазон, не точка |
| 2025 | Самозанятые | 25 212 | заявки, подмножество B2C | `[Data, Tier 1]` годовой отчёт | тренд, не складывать |
| 2026-04-01 | Самозанятые | 16,188 млн | зарегистрированные лица | `[Data, Tier 1]` [ФНС](https://analytic.nalog.gov.ru/) | контекст, не TAM |
| 2026-04-01 | ИП | 4,918 млн | лица, частично пересекаются с НПД | `[Data, Tier 1]` ФНС | не суммировать |

`[Estimate]` Диапазон 74,5–86,0 тыс. — 55% от российских и всех заявок. Это **transaction TAM**, не уникальные покупатели: один заявитель может подать несколько заявок.

## TAM / SAM / SOM

| Контур | Формула | Результат | Тип и уверенность |
|---|---|---:|---|
| B2C TAM | 74,5–86,0 тыс. × 7 900 ₽ | 588–679 млн ₽/год | `[Estimate]` средняя |
| B2C SAM | TAM × 65% simple × 35% WTP | 134–155 млн ₽/год | `[Estimate based on Assumptions]` низкая |
| B2C SOM, год 1 | 120–240 оплат × 7 900 ₽ | 0,95–1,90 млн ₽ | `[Assumption: operating target]` низкая |
| B2B TAM | 254–1 054 firm-equivalents × 600 тыс. ₽ ACV | 153–632 млн ₽ ARR | `[Estimate based on Assumptions]` низкая |
| B2B SAM | 75–150 практик × 600 тыс. ₽ | 45–90 млн ₽ ARR | `[Assumption]` низкая |
| B2B SOM | 3–8 фирм × 50 тыс. ₽ × 12 мес. | 1,8–4,8 млн ₽ ARR | `[Assumption: operating target]` низкая |

`[Assumption]` Simple share 65% и WTP 35% не подтверждены. `[Assumption]` SOM — цель мощности, не доказанно достижимая доля. `[Data gap]` Актуального census IP-фирм с объёмом дел нет; B2B использует proxy.

## Цена, пошлины и unit economics

`[Data, Tier 1, accessed 2026-08-28]` Минимальные пошлины на один класс: 4 000 + 13 000 + 18 000 = 35 000 ₽. [Роспатент](https://rospatent.gov.ru/ru/stateservices/gosudarstvennaya-registraciya-tovarnogo-znaka-znaka-obsluzhivaniya-kollektivnogo-znaka-i-vydacha-svidetelstv-na-tovarnyy-znak-znak-obsluzhivaniya-kollektivnyy-znak-ih-dublikatov).

`[Estimate]` Полный минимум: 35 000 + 7 900 = **42 900 ₽**; пошлины — 81,6%. `[Opinion]` Покупатель оценивает ценность предотвращения ошибки относительно полного необратимого платежа.

| Метрика | Значение | Статус |
|---|---:|---|
| Цена | 7 900 ₽ | `[Assumption: founder price]` |
| Variable COGS без юриста | 500–1 500 ₽ | `[Assumption]` |
| Gross profit до CAC | 6 400–7 400 ₽ | `[Estimate]` |
| Gross margin | 81–94% | `[Estimate]`, без founder labor |
| CAC ceiling | 2 000–2 300 ₽ | `[Assumption]` |

`[Assumption]` CAC ceiling резервирует примерно 4,1–5,4 тыс. ₽ на поддержку, возвраты, налоги, founder labor и эскалацию. Формула: `price − payment/AI/data COGS − support/refund reserve − CAC > 0`. Фактический contribution margin появится после первых 20 оплат.

## Решение и success gates

`[Opinion]` Статус **жёлто-зелёный: продолжать validation, не расширять scope до доказательства спроса**.

`[Assumption]` Gates: 20 платных дел; затем 100+ дел; один канал с CAC ≤2,3 тыс. ₽; первоначальная цель completion intake→package ≥60%; blinded comparison с юристом.

## Стратегические связи

- `[Opinion]` Высокие пошлины усиливают free risk map до checkout.
- `[Opinion]` Низкая частота B2C требует lifecycle revenue: ответы, статусы, мониторинг.
- `[Opinion]` B2B 50 тыс. ₽ рациональнее при 10–20+ делах/мес.; launch должен проверить usage-based pricing.
- `[Opinion]` Инвесторская категория: операционная платформа защиты бренда для новой массовой группы предпринимателей.

## Data Gaps

| Пробел | Влияние | Закрытие |
|---|---|---|
| WTP при чеке 42 900 ₽ | может обнулить SAM | checkout smoke test и 20 продаж |
| Доля simple cases | определяет automation fit | разметка 100 дел юристом |
| CAC и конверсия | определяют масштаб | cohort analytics |
| COGS/support/refunds | определяют маржу | time tracking 20 дел |
| Число и объём IP-фирм | ослабляют B2B size | 15 интервью + выборка |

## Red Flags

- `[Data]` Интервью, пользователи и продажи отсутствуют; спрос не подтверждён.
- `[Risk]` Сырые паспортные данные в иностранной LLM могут блокировать production launch.

## Yellow Flags

- `[Assumption]` WTP, simple share, CAC, COGS, completion и B2B price не валидированы.
- `[Data quality]` У Роспатента разные знаменатели; TAM остаётся диапазоном транзакций.
- `[Market risk]` Бесплатный государственный pre-check может снизить ценность базового self-service.
