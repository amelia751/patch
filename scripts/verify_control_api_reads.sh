#!/usr/bin/env bash
# Dynamic verifier for the console schema + control plane reachability.
#
# Brings up local Postgres, applies the console migrations and seed, serves
# the wired control plane, and asserts the store answers. Workflow dashboard
# reads (/v1/changes, /v1/runs, /v1/fleet) are not in this schema yet.
#
# When Docker is unavailable it SKIPS with exit 0 and says so. A skipped
# integration check is honest; one that "passes" without ever connecting is not.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="db/docker-compose.yml"
DB_PORT="${PATCHAPI_DB_PORT:-55432}"
DSN="postgresql://patchapi:patchapi_local_dev@127.0.0.1:${DB_PORT}/patchapi"

SERVER_PID=""
LOG_FILE=""
PORT=""

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

skip() {
  echo
  echo "SKIP: $*"
  exit 0
}

step() {
  echo
  echo "== $*"
}

cleanup() {
  local status=$?
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.5
    done
    kill -9 "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ $status -ne 0 && -n "$LOG_FILE" && -s "$LOG_FILE" ]]; then
    echo "--- control plane log ---" >&2
    tail -40 "$LOG_FILE" >&2
  fi
  [[ -n "$LOG_FILE" ]] && rm -f "$LOG_FILE"
  return $status
}
trap cleanup EXIT

echo "== control-plane read path verifier =="
echo "repo: $REPO_ROOT"

command -v docker >/dev/null 2>&1 || skip "docker is not on PATH"
docker info >/dev/null 2>&1 || skip "the docker daemon is not running"
command -v curl >/dev/null 2>&1 || fail "curl not on PATH"

step "start Postgres"
docker compose -f "$COMPOSE_FILE" up -d >/dev/null
for _ in $(seq 1 60); do
  if docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_isready -U patchapi -d patchapi >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_isready -U patchapi -d patchapi >/dev/null 2>&1 ||
  fail "Postgres did not become ready"

step "apply migrations and demo seed"
PYTHONPATH=db/src uv run --quiet python -m patchapi_db migrate | tail -1
PYTHONPATH=db/src uv run --quiet python -m patchapi_db seed | tail -1

step "serve the wired control plane"
PORT="$(uv run --quiet python -c '
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
')"
BASE="http://127.0.0.1:${PORT}"
LOG_FILE="$(mktemp -t patchapi-reads)"
DATABASE_URL="$DSN" HOST=127.0.0.1 PORT="$PORT" \
  uv run --package patchapi-state patchapi-serve >"$LOG_FILE" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    fail "the control plane exited before serving"
  fi
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/healthz" || true)" == "200" ]]; then
    break
  fi
  sleep 1
done
echo "listening on $BASE"

step "readiness reports the store as reachable"
# Not `-f`: /readyz answers 503 while any probe is unsatisfied, and that body is
# the report itself. The event transport is legitimately unwired until Pub/Sub
# exists (roadmap phase 4), so this asserts on the store probes specifically
# rather than on the overall status.
curl -sS "$BASE/readyz" -o /tmp/patchapi_reads_body
uv run --quiet python -c '
import json

body = json.load(open("/tmp/patchapi_reads_body"))
checks = {check["name"]: check for check in body["checks"]}
for name in ("workflow_state_store", "dashboard_read_model", "postgres"):
    assert checks[name]["ready"], f"{name} not ready: {checks[name]}"
print("store probes ready:", ", ".join(sorted(checks)))
'

step "console seed is queryable"
PYTHONPATH=db/src uv run --quiet python -m patchapi_db sql <<'SQL'
SELECT u.email, i.username, c.account_login, p.name, r.full_name
FROM users u
JOIN user_identities i ON i.user_id = u.id AND i.provider = 'github'
JOIN github_connections c ON c.user_id = u.id
JOIN projects p ON p.owner_id = u.id
JOIN project_repositories r ON r.project_id = p.id
WHERE u.id = '5eedda7a-0001-4000-8000-000000000001';
SQL

echo
echo "PASS: console schema is applied and the control plane reaches Postgres"
echo "SKIP: /v1/changes /v1/runs /v1/fleet — workflow tables are not in this schema yet"

