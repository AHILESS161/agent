# Конкурентный ландшафт «Регистры»

**Срез цен и страниц:** 28 августа 2026 года  
**Уверенность:** средняя для публичных цен; низкая–средняя для traction  
**Правило:** публичная vendor page — primary-for-price, но показатели traction классифицируются как `[Vendor primary / low verification]`, а не независимый Tier 2. Метрики несопоставимы по периоду и определению.

## Вердикт

`[Opinion based on competitor scan]` Рынок занят цифровыми сервисами, патентными бюро, государственными инструментами и AI-поисковиками. Свободного пространства «регистрация товарного знака онлайн» не обнаружено. Окно есть в более узком обещании:

> Понятно решить, стоит ли подавать знак; получить проверяемое объяснение рисков и корректный комплект документов; при необходимости передать уже собранное дело юристу без повторной работы.

`[Assumption]` Цена «Регистры» 7 900 ₽ — рабочий вход, но не moat. `[Data, primary-for-price, accessed 2026-08-28]` Entry-тариф Brandside — 11 500 ₽. `[Estimate]` Разница 3 600 ₽ составляет 8,4% минимального полного чека 42 900 ₽.

## Прямые конкуренты

| Игрок | Продукт | Цена без пошлин | Аудитория | Funding | Traction | Сила | Окно для «Регистры» |
|---|---|---:|---|---|---|---|---|
| Online Patent | end-to-end кабинет + поверенные | `[Data, primary-for-price]` 27 490 ₽; 49 990 ₽ | SMB, компании | `[Data gap]` | `[Vendor primary / low verification]` 3 683 ТЗ в 2025; 120k+ users | масштаб/lifecycle | scope/цена |
| Гардиум / Gardium.Pro | IP-фирма + enterprise SaaS | `[Data gap]` по запросу | IP-команды, enterprise | `[Data gap]` | `[Vendor primary / low verification]` 13k клиентов; 10k+ проверок/мес. | портфель/роли | сложность/цена |
| Brandside | цифровая подача + эксперты | `[Data, primary-for-price]` 11 500–44 900 ₽ | B2C, SMB | `[Data gap]` | `[Vendor primary / low verification]` 97% success, denominator unknown | entry/human | evidence/scope |
| ЕДРИД | подача + эксперт; IP SaaS | `[Data, primary-for-price]` около 29 000 ₽ | B2C/SMB | `[Data gap]` | `[Data gap]` | lifecycle | menu complexity |
| NOVIK | поверенный | `[Data, primary-for-price]` около 20 000 ₽ | предприниматели, SMB | `[Data gap]` | `[Vendor primary / low verification]` 1k+ проектов; 700+ клиентов | human/price | automation |
| RegТЗ | бюро + калькуляторы | `[Data, primary-for-price]` 30 000 ₽ подача; 14 000 ₽ поиск | SMB | `[Data gap]` | `[Data gap]` | понятная услуга | traditional workflow |
| PATENTUS | IP-фирма + кабинет | `[Data, primary-for-price]` 29 900–64 900 ₽ | SMB, корпорации | `[Data gap]` | `[Vendor primary / low verification]` 15k+ ТЗ; 600+ судов | reputation | heavy simple-case path |

Публичные страницы: [Online Patent](https://onlinepatent.ru/trademarks/), [Gardium.Pro](https://gardium.pro/), [Brandside](https://brandside.ru/), [NOVIK](https://www.dsnovik.ru/service/registracia_tz), [PATENTUS](https://patentus.ru/).

## Новые и платформенные угрозы

Все уровни угроз и стратегические следствия в этом разделе — `[Opinion/Risk]`; наличие продукта подтверждает предложение, но не его adoption или качество.

| Угроза | Почему важна | Уровень |
|---|---|---|
| МСП.РФ, Госуслуги, Роспатент | могут сделать подготовку и подачу бесплатной | Высокий |
| xyma, «Брендоскоп», ai.Prilan | AI-анализ и низкая цена становятся commodity | Средний–высокий |
| POISKZNAKOV, Linkmark | дешёвый профессиональный поиск обесценивает список совпадений | Средний |
| Банки и маркетплейсы | владеют дистрибуцией и могут встроить чужой сервис | Высокий |
| Универсальные LLM | бесплатный черновик для price-sensitive клиента | Средний |
| Excel + Word + CRM | достаточный status quo малого B2B-объёма | Высокий для тарифа 50k |

## Commodity и конкурентное окно

`[Opinion, high confidence only for basic functions]` Коммодитизируются exact-match list, basic pre-check, draft generation, guided form и электронная отправка. `[Data gap]` Качественная юридическая оценка сходства, МКТУ и документов commodity не признана.

Окно «Регистры»:

1. **Объяснимость:** риск привязан к знаку, классу, источнику и основанию.
2. **МКТУ от бизнеса:** видно, что защищено и исключено.
3. **Evidence pack:** входные данные, версии источников, конфликты, выводы, DOCX/ZIP, журнал.
4. **Human review как отдельный продукт:** ясные SLA, scope и ответственность.
5. **Маршрут после подачи:** статус, дедлайн, owner и переход к ответу.
6. **B2B-контур:** роли, шаблоны, пакетная работа, audit trail, утверждение юристом.

## Moat assessment

Вся оценка moat — `[Opinion/Assumption]`, которую нужно проверять retention, повторным использованием и willingness-to-switch.

| Преимущество | Сейчас | Потенциал | Как строить |
|---|---|---|---|
| LLM/технология | Низкий | Низкий–средний | модели доступны всем |
| Цена | Низкий | Низкий | легко скопировать |
| Workflow | Низкий | Средний | intake → решение → документы → ответ |
| Данные качества | Нет | Средний–высокий | размеченные расхождения AI/юриста и outcomes |
| Доверие | Нет | Средний | методика, юрист, кейсы, ограничения |
| Дистрибуция | Нет | Средний | партнёры в момент создания бренда |
| B2B switching costs | Нет | Средний | шаблоны, история, портфель, роли |

## Battle cards

Все battle cards — `[Opinion]`, производная от competitor scan, не customer-tested copy.

**Против бесплатной подачи:** продавать не отправку формы, а решение до оплаты пошлин, корректный scope и готовность к запросу.

**Против юрфирмы:** не обещать заменить юриста. Простой кейс — быстрее и прозрачнее; сложный — структурированно передать специалисту.

**Против Online Patent/Brandside:** показывать образец результата, источники и scenario-price до оплаты. Не позиционироваться «тоже онлайн, но дешевле».

**Против универсального AI:** актуальные реестры, воспроизводимость, официальные документы, правила эскалации и human approval.

**Против Gardium.Pro:** малый B2B, один узкий workflow, usage-based вход и экспорт без lock-in.

## Стратегические связи

Все связи ниже — `[Opinion]`.

- Чем лучше государственная подача, тем ценнее pre-filing решение и post-filing сопровождение.
- Недоверие к AI задаёт дизайн: AI делает работу, доказательства видны, итог утверждает человек.
- B2C может стать источником данных и lifecycle-выручки только при законной безопасной обработке.
- У B2C и B2B общий движок, но разные интерфейсы, ответственность и критерии покупки.

## Data Gaps

| Пробел | Влияние | Закрытие |
|---|---|---|
| Comparable package scope | искажает price comparison | mystery shopping по единому кейсу |
| Independent traction/funding | мешает оценить силу игроков | реестры, интервью, отчётность |
| Conversion/CAC/churn | мешает оценить GTM | partner/customer interviews |
| Accuracy и отказность | мешает product benchmark | blind case comparison |
| Дата недатированных counters | риск stale metrics | quarterly capture с timestamp |

## Red Flags

- `[Platform risk]` Государство и крупные экосистемы могут бесплатно встроить basic filing/pre-check.
- `[Competitive risk]` Incumbent с поверенными может субсидировать дешёвый self-service.

## Yellow Flags

- `[Data quality]` Цены различаются по scope; прямое сравнение чек-в-чек ограничено.
- `[Data quality]` Traction — marketing metrics компаний без независимого подтверждения.
- `[Moat risk]` Цена и базовый AI легко копируются.

## Sources

Все цены accessed 28.08.2026: [Online Patent](https://onlinepatent.ru/trademarks/), [Gardium.Pro](https://gardium.pro/), [Brandside](https://brandside.ru/prices), [ЕДРИД](https://edrid.ru/price.html), [NOVIK](https://www.dsnovik.ru/service/registracia_tz), [RegТЗ](https://regtz.ru/pricing/), [PATENTUS](https://patentus.ru/sroki-i-tzeny/registratzia-tovarnih-znakov/). Новые продукты: [xyma](https://xyma.ru/), [Брендоскоп](https://brendoskop.ru/), [ai.Prilan](https://prilan.ru/trademarks). Государственная угроза: [Роспатент о МСП.РФ](https://rospatent.gov.ru/ru/news/26-02-2025-rospatent-zapustil-servis-dlya-uproshchennoy-registracii-tovarnyh-znakov), `[Data, Tier 1, Stale >18 months]`.
