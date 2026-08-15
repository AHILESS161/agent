# Запуск демо-стенда и доступ извне

> **Проверено 15.08.2026.** Актуальные роли: клиент создаёт заявку,
> администратор сразу видит её и назначает юриста; назначенный юрист работает с
> делом в профессиональном интерфейсе. Ограничения перечислены в
> [`current-state.md`](current-state.md).

Документ описывает, как поднять систему локально и как безопасно дать
временный доступ внешнему тестировщику.

---

## 1. Локальный запуск

### Через Docker Compose (рекомендуется)

```bash
cp .env.example .env
docker compose up --build
```

Поднимаются три сервиса: API (8000), веб-интерфейс (3000), Redis (6379).

**Важно:** схему БД создаёт Alembic, а не приложение. При первом запуске
выполните миграции и загрузку демо-данных:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed.init_db
docker compose exec api python -m scripts.ingest_knowledge
```

Шаг `ingest_knowledge` обязателен: правовой анализ читает базу знаний
из БД, а не из файлов. Без индексации анализ по статье 1483 вернёт
«Недостаточно подтверждённых данных для вывода.»

### Без Docker

Backend:

```bash
cd backend
python -m venv ../venv
../venv/Scripts/python -m pip install -r requirements.txt
../venv/Scripts/python -m alembic upgrade head
../venv/Scripts/python -m app.seed.init_db
../venv/Scripts/python -m scripts.ingest_knowledge
../venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Frontend (в другом терминале):

```bash
cd frontend
npm ci
npm run dev
```

Интерфейс: <http://localhost:3000> · API-документация: <http://localhost:8000/docs>

### Проверка работоспособности

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

`/health` подтверждает, что процесс жив. `/ready` проверяет обязательные
зависимости — БД и файловое хранилище — и отвечает 503, если система не
готова обслуживать запросы.

---

## 2. Учётные записи демо-стенда

Создаются скриптом `app.seed.init_db`:

| Логин | Пароль | Роль |
|---|---|---|
| `lawyer@demo.ru` | `demo123` | Специалист (юрист) |
| `admin@demo.ru` | `demo123` | Администратор |
| `manager@demo.ru` | `demo123` | Менеджер |
| `client@demo.ru` | `demo123` | Клиент |

**Пароли демонстрационные.** Перед выдачей ссылки наружу смените их либо
создайте отдельные учётные записи:

```bash
# Создание пользователя доступно только администратору
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login/json \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.ru","password":"demo123"}' | jq -r .access_token)

curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"tester@example.com","password":"<надёжный-пароль>","full_name":"Тестировщик","role":"lawyer"}'
```

Самостоятельная регистрация закрыта намеренно: эндпоинт принимает поле
`role`, и в открытом виде он позволял любому желающему назначить себе
роль администратора.

---

## 3. Временный доступ извне

URL туннеля **не должен** попадать в исходный код — он задаётся
переменной окружения и меняется при каждом запуске.

### Cloudflare Tunnel (без регистрации)

```bash
cloudflared tunnel --url http://localhost:3000
```

Команда печатает временный адрес вида `https://<случайно>.trycloudflare.com`.

Frontend проксирует `/api` на backend, поэтому наружу достаточно вывести
только порт 3000. Vite настроен с `allowedHosts: true` — произвольный хост
туннеля не будет отклонён.

### ngrok

```bash
ngrok http 3000
```

### Если backend вынесен отдельно

```bash
# frontend будет обращаться к указанному адресу
VITE_API_URL=https://<адрес-backend> npm run dev
```

И добавьте адрес туннеля в CORS:

```bash
CORS_ORIGINS=["https://<адрес-туннеля>"]
```

---

## 4. Обязательный чек-лист перед выдачей ссылки

- [ ] `DEMO_MODE=true` — запрещает реальную подачу заявки и внешние действия
- [ ] `ENABLE_REAL_SUBMISSION=false`
- [ ] `RATE_LIMIT_ENABLED=true`
- [ ] `SECRET_KEY` заменён на случайный: `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] `DEBUG=false` — иначе в ответах могут появиться подробности ошибок
- [ ] Пароли демо-учёток изменены
- [ ] `CORS_ORIGINS` содержит адрес туннеля и не содержит `*`
- [ ] `LLM_API_KEY` — отдельный ключ с лимитом расходов, не основной
- [ ] В хранилище `FILE_STORAGE_PATH` нет посторонних документов

Проверить фактический режим:

```bash
curl http://localhost:8000/ready
curl -X POST http://localhost:8000/api/v1/applications/1/submit -H "Authorization: Bearer $TOKEN"
# Ожидается 403 с текстом про демонстрационный режим
```

---

## 5. Что запрещено в демо-режиме

При `DEMO_MODE=true` система **не выполняет**:

- фактическую подачу заявки в Роспатент;
- отправку писем реальным адресатам;
- изменение данных во внешних системах.

Режим поиска определяется `FIPS_PROVIDER`: `mock` использует автономный
демо-датасет; `rospatent_public` выполняет ограниченный read-only поиск
регистраций и заявок; `fips` требует договорного ключа официального API.
Интерфейс и результаты анализа сохраняют режим `demo`, `limited` или `real`,
чтобы публичный поиск нельзя было принять за официальный полный поиск.

---

## 6. Удаление демо-данных

Демо-стенд хранит загруженные документы на диске и записи в БД.
После тестирования:

```bash
# Остановить сервисы
docker compose down

# Удалить БД и загруженные файлы
rm -f backend/trademark.db
rm -rf backend/storage/
```

Загруженные тестировщиком документы могут содержать персональные данные,
поэтому хранилище следует очищать вместе с базой, а не по отдельности.
