#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

if [ ! -f .env.production ]; then
  echo "Не найден .env.production" >&2
  exit 1
fi

BACKUP_DIR=${BACKUP_DIR:-"$ROOT_DIR/backups"}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$BACKUP_DIR"

COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"

# Пароль не передаётся командной строкой: pg_dump получает его из окружения
# контейнера PostgreSQL. Дамп создаётся в custom-формате для pg_restore.
$COMPOSE exec -T postgres sh -c \
  'pg_dump --format=custom --no-owner --no-privileges --username="$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$BACKUP_DIR/database-$STAMP.dump"

docker run --rm \
  -v registr_documents_data:/source:ro \
  -v "$BACKUP_DIR:/backup" \
  alpine:3.20 \
  tar -czf "/backup/documents-$STAMP.tar.gz" -C /source .

# Локально держим семь последних комплектов. Внешняя зашифрованная копия
# настраивается отдельно (restic/S3 в российском регионе).
find "$BACKUP_DIR" -type f -name 'database-*.dump' | sort -r | sed -n '8,$p' | xargs -r rm -f
find "$BACKUP_DIR" -type f -name 'documents-*.tar.gz' | sort -r | sed -n '8,$p' | xargs -r rm -f

echo "Созданы резервные копии с меткой $STAMP в $BACKUP_DIR"
