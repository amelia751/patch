#!/usr/bin/env bash
# Cloud SQL Auth Proxy for local processes. Same instance Cloud Run uses.
#
# Listens on 127.0.0.1:5433. DATABASE_URL is .secrets/database-url-proxy.txt.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONNECTION_NAME="${PATCHAPI_CLOUDSQL_CONNECTION:-patch-505223:us-central1:patchapi-console}"
PORT="${PATCHAPI_CLOUDSQL_PROXY_PORT:-5433}"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"
BIN="$ROOT/.local/cloud-sql-proxy"

if [[ ! -f "$KEY_FILE" ]]; then
  printf 'missing service-account key: %s\n' "$KEY_FILE" >&2
  exit 1
fi
export GOOGLE_APPLICATION_CREDENTIALS="$KEY_FILE"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  printf 'cloud-sql-proxy already listening on 127.0.0.1:%s\n' "$PORT"
  exit 0
fi

if [[ ! -x "$BIN" ]]; then
  mkdir -p "$ROOT/.local"
  arch="$(uname -m)"
  case "$arch" in
    arm64) proxy_arch=darwin.arm64 ;;
    x86_64) proxy_arch=darwin.amd64 ;;
    *) printf 'unsupported arch %s\n' "$arch" >&2; exit 1 ;;
  esac
  curl -fsSL -o "$BIN" \
    "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.15.2/cloud-sql-proxy.${proxy_arch}"
  chmod +x "$BIN"
fi

exec "$BIN" "$CONNECTION_NAME" --port="$PORT" --address=127.0.0.1
