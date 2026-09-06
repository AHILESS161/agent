#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

if [ ! -f .env.production ]; then
  echo "Не найден .env.production. Скопируйте .env.production.example и заполните секреты." >&2
  exit 1
fi

COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"

# Обновление кода выполняется только fast-forward: локальные изменения на
# сервере не должны молча смешиваться с опубликованной версией.
git pull --ff-only

$COMPOSE build
if $COMPOSE ps --status running --services | grep -qx postgres; then
  bash deploy/backup.sh
fi
mkdir -p "${BACKUP_DIR:-backups}"
exec 9>"${BACKUP_DIR:-backups}/.maintenance.lock"
flock -n 9 || exit 1
$COMPOSE stop -t 150 api worker
$COMPOSE up -d postgres
$COMPOSE run --rm migrate
$COMPOSE up -d --remove-orphans --wait --wait-timeout 180
$COMPOSE ps

$COMPOSE exec -T api curl --fail --silent http://localhost:8000/ready
domain=$(sed -n 's/^DOMAIN=//p' .env.production | tr -d '\r')
curl --fail --silent --show-error --max-time 15 "https://$domain/ready"
echo "Deployment ready: schema, storage and worker checked"
