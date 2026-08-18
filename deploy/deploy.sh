#!/usr/bin/env sh
set -eu

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
$COMPOSE up -d postgres
$COMPOSE run --rm migrate
$COMPOSE up -d --remove-orphans
$COMPOSE ps

echo "Развёртывание завершено. Проверьте https://$(sed -n 's/^DOMAIN=//p' .env.production)/healthz"
