# Демо-стенд `registr-ai.ru`

Актуально на 5 сентября 2026 года.

## Размещение

- домен: `registr-ai.ru`, дополнительное имя `www.registr-ai.ru`;
- публичный IPv4: `80.78.246.76`;
- ОС: Ubuntu 24.04 LTS;
- конфигурация: 3 vCPU, 3 ГБ RAM, 60 ГБ NVMe и 2 ГБ swap;
- каталог приложения: `/opt/registr`;
- запуск: `docker-compose.prod.yml`;
- production-секреты: `/opt/registr/.env.production`, права `600`, файл не хранится в Git;
- пароли демонстрационных аккаунтов: `/root/registr-demo-credentials.txt`, права `600`.

Стенд работает в безопасном демонстрационном режиме: `DEMO_MODE=true` и
`ENABLE_REAL_SUBMISSION=false`. Фактическая отправка заявок во внешние системы
запрещена.

## Сервисы

Docker Compose запускает PostgreSQL, миграции Alembic, FastAPI, отдельный worker,
статический frontend на nginx и Caddy. Наружу открыты только `80` и `443`; база
данных и API доступны лишь во внутренней Docker-сети. SSH работает на порту `22`.

Caddy получает TLS-сертификат автоматически после того, как A-записи домена и
`www` начинают разрешаться в `80.78.246.76`.
Запросы к `www.registr-ai.ru` перенаправляются на канонический адрес `https://registr-ai.ru`.

## Проверка состояния

```bash
cd /opt/registr
docker compose --env-file .env.production -f docker-compose.prod.yml ps -a
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T api \
  curl -fsS http://localhost:8000/ready
```

Ожидаемый ответ API содержит `"status":"ready"`. Контейнер `migrate` должен
завершиться с кодом `0`; остальные контейнеры должны работать и стать `healthy`.

## Обновление стенда

```bash
cd /opt/registr
git pull --ff-only
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

После изменения правовых материалов повторно загрузите RAG-базу:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T api \
  python -m scripts.ingest_knowledge
```

## Диагностика

```bash
cd /opt/registr
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 api worker caddy
free -h
df -h
```

Не публикуйте `.env.production` и файл демонстрационных паролей. Для передачи
доступа коллеге создавайте отдельную учётную запись либо передавайте только
пароль нужной роли через защищённый канал.

## Исправления, выявленные первым production-запуском

- списки `CORS_ORIGINS` теперь принимают документированный формат через запятую;
- миграция заранее создаёт PostgreSQL enum `casepriority`;
- production-образ включает синхронный драйвер `psycopg` для seed-скрипта;
- healthcheck nginx использует `127.0.0.1`, чтобы не зависеть от IPv6-разрешения
  имени `localhost` внутри Alpine.
- nginx явно задаёт каталог `/usr/share/nginx/html` и `index.html`, поэтому корень домена открывает SPA;
- worker использует проверку живого процесса вместо HTTP-проверки API: фоновый процесс не открывает HTTP-порт.
