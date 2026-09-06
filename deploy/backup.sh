#!/usr/bin/env bash
# A short maintenance window provides a consistent DB/blob checkpoint.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
root=$(pwd)
env_file=${ENV_FILE:-.env.production}
compose=(docker compose --env-file "$env_file" -f docker-compose.prod.yml)
backup_dir=${BACKUP_DIR:-"$root/backups"}
mkdir -p "$backup_dir"
backup_dir=$(cd "$backup_dir" && pwd)
exec 9>"$backup_dir/.maintenance.lock"
flock -n 9 || { echo 'Another maintenance operation is running' >&2; exit 1; }
if [[ ${BACKUP_LOCAL_ONLY:-false} != true ]]; then
  : "${RESTIC_REPOSITORY:?Configure an off-host restic repository}"
  : "${RESTIC_PASSWORD_FILE:?Configure a protected restic password file}"
  case "$RESTIC_REPOSITORY" in s3:*|sftp:*|rest:*|azure:*|gs:*|b2:*) ;; *)
    echo 'Off-host restic repository required' >&2; exit 1;; esac
  command -v restic >/dev/null
fi
stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
partial=$(mktemp -d "$backup_dir/.partial-$stamp-XXXXXX")
resume=()
running_services=$("${compose[@]}" ps --status running --services)
while read -r service; do
  case "$service" in api|worker) resume+=("$service");; esac
done <<< "$running_services"
cleanup() {
  result=$?
  trap - EXIT
  if ((${#resume[@]})); then "${compose[@]}" start "${resume[@]}" || result=1; fi
  if ((result)); then echo "Backup failed; inspect incomplete sets in $backup_dir" >&2; fi
  exit "$result"
}
trap cleanup EXIT
if ((${#resume[@]})); then "${compose[@]}" stop -t 150 "${resume[@]}"; fi
"${compose[@]}" exec -T postgres sh -c \
  'pg_dump --format=custom --no-owner --no-privileges --username="$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$partial/database.dump"
"${compose[@]}" exec -T postgres pg_restore --list < "$partial/database.dump" > /dev/null
"${compose[@]}" run --rm --no-deps -T api tar -czf - -C /data/documents . > "$partial/documents.tar.gz"
tar -tzf "$partial/documents.tar.gz" > /dev/null
printf 'format=1\ncreated_utc=%s\nrevision=%s\n' "$stamp" "$(git rev-parse HEAD)" > "$partial/manifest"
(cd "$partial" && sha256sum database.dump documents.tar.gz manifest > SHA256SUMS)
bundle="$backup_dir/backup-$stamp"
mv "$partial" "$bundle"
if ((${#resume[@]})); then "${compose[@]}" start "${resume[@]}"; resume=(); fi
if [[ ${BACKUP_LOCAL_ONLY:-false} != true ]]; then
  restic backup "$bundle" --tag registr --json > "$bundle/restic-receipt.json"
  restic check
  touch "$bundle/OFFSITE_OK"
fi
echo "Consistent backup: $bundle"
# No automatic deletion until restore and retention are verified.
