#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
compose=(docker compose --env-file "${ENV_FILE:-.env.production}" -f docker-compose.prod.yml)
mkdir -p "${BACKUP_DIR:-backups}"
exec 9>"${BACKUP_DIR:-backups}/.maintenance.lock"
flock -n 9 || exit 1
resume=()
running_services=$("${compose[@]}" ps --status running --services)
while read -r service; do
  case "$service" in api|worker) resume+=("$service");; esac
done <<< "$running_services"
cleanup() { if ((${#resume[@]})); then "${compose[@]}" start "${resume[@]}"; fi; }
trap cleanup EXIT
if ((${#resume[@]})); then "${compose[@]}" stop -t 150 "${resume[@]}"; fi
"${compose[@]}" run --rm --no-deps -T api python -m scripts.storage_gc --writers-stopped --retention-days "${GC_RETENTION_DAYS:-7}"
