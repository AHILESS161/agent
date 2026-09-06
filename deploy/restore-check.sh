#!/usr/bin/env bash
# Always restores into an isolated disposable container, never the live database.
set -euo pipefail
bundle=$(cd "${1:?Pass a completed backup directory}" && pwd)
root=$(cd "$(dirname "$0")/.." && pwd)
(cd "$bundle" && sha256sum --check SHA256SUMS)
name="registr-restore-check-$(date +%s)-$$"
started=$SECONDS
docker run -d --name "$name" --network none --memory 512m --cpus 1 \
  -e POSTGRES_PASSWORD=isolated-restore-only postgres:16-alpine > /dev/null
trap 'docker rm -fv "$name" > /dev/null' EXIT
ready=false
for attempt in $(seq 1 60); do
  if docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; then ready=true; break; fi
  sleep 1
done
[[ $ready == true ]] || exit 1
docker exec -i "$name" pg_restore --exit-on-error --no-owner --no-privileges -U postgres -d postgres < "$bundle/database.dump"
python3 "$root/deploy/verify_backup.py" "$name" "$bundle/documents.tar.gz"
echo "Restore check finished in $((SECONDS - started)) seconds"
