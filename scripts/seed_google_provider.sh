#!/usr/bin/env bash
# Apply provider migrations and upsert the Google Cloud registry row (no owner).
# Does not connect catalog or changes endpoints — paste those URLs in /provider.
#
# Uses Cloud SQL via the Auth Proxy when .secrets/database-url-proxy.txt exists.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Homebrew libpq is keg-only; the migrate runner shells out to `psql`.
if ! command -v psql >/dev/null 2>&1; then
  for candidate in /opt/homebrew/opt/libpq/bin /usr/local/opt/libpq/bin; do
    if [[ -x "$candidate/psql" ]]; then
      PATH="$candidate:$PATH"
      export PATH
      break
    fi
  done
fi
if ! command -v psql >/dev/null 2>&1; then
  printf 'psql is not on PATH. Install libpq (brew install libpq) or use Docker.\n' >&2
  exit 1
fi

PROXY_DSN_FILE="$ROOT/.secrets/database-url-proxy.txt"
if [[ -z "${DATABASE_URL:-}" && -f "$PROXY_DSN_FILE" ]]; then
  export DATABASE_URL
  DATABASE_URL="$(tr -d '\n' < "$PROXY_DSN_FILE")"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  printf 'DATABASE_URL is unset.\n' >&2
  printf 'Start the proxy, then re-run:\n' >&2
  printf '  ./scripts/run_cloud_sql_proxy.sh\n' >&2
  printf '  ./scripts/seed_google_provider.sh\n' >&2
  exit 1
fi

if [[ "$DATABASE_URL" == *127.0.0.1:5433* ]] || [[ "$DATABASE_URL" == *localhost:5433* ]]; then
  if ! lsof -nP -iTCP:5433 -sTCP:LISTEN >/dev/null 2>&1; then
    printf 'Cloud SQL proxy is not listening on 127.0.0.1:5433.\n' >&2
    printf 'In another terminal: ./scripts/run_cloud_sql_proxy.sh\n' >&2
    exit 1
  fi
fi

PYTHONPATH=db/src uv run python -m patchapi_db migrate
# Only the Google profile. The demo console seed is a different concern and
# may already exist on Cloud SQL with conflicting keys.
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$ROOT/db/seeds/0002_google_provider.sql"

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -At -c "
SELECT slug || '|' || name || '|' ||
       CASE WHEN owner_user_id IS NULL AND owner_organization_id IS NULL THEN 'unowned' ELSE 'owned' END || '|' ||
       CASE WHEN verified THEN 'verified' ELSE 'unverified' END
FROM providers WHERE slug = 'google';
" | tee /dev/stderr | grep -qx 'google|Google Cloud|unowned|verified'
