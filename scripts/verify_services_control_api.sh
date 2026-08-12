#!/usr/bin/env bash
# Dynamic verifier for services/control_api (setup.md T-services-control_api).
#
# Lints and unit-tests the tree, then boots the real ASGI application with
# uvicorn on an ephemeral port and probes it over HTTP: liveness returns the
# expected JSON, the OpenAPI document describes the whole surface, the unwired
# service fails closed on readiness and on every product route, and the process
# shuts down cleanly on SIGTERM. Exits non-zero on any failure and records the
# outcome in the shared setup ledger.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_services_control_api.sh"
STATUS="FAIL"
SERVER_PID=""
SERVER_LOG=""

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-services-control_api","status":"%s","command":"%s","at":"%s"}\n' \
    "$STATUS" "$COMMAND" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LEDGER"
}

teardown() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  [[ -n "$SERVER_LOG" ]] && rm -f "$SERVER_LOG"
  record
}
trap teardown EXIT

step() { printf '\n== %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

if ! command -v uv >/dev/null 2>&1; then
  fail "uv is not installed (see setup.md §3)"
fi
if ! command -v curl >/dev/null 2>&1; then
  fail "curl is not installed"
fi

# The service imports the contracts from the checkout rather than from an
# installed wheel, so the probe exercises the source this tree owns.
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/services/control_api/src"

# Preferred path: this package installed from the workspace, which also proves
# it is a real workspace member. Scoped with `--package` rather than
# `--all-packages` so a sibling tree that is mid-flight cannot fail this tree's
# verification; if even the scoped install is unusable, fall back to an
# isolated environment built from this package's own pinned dependencies so the
# service stays verifiable.
#
# Set PATCHAPI_VERIFY_ISOLATED=1 to exercise the fallback deliberately.
step "environment"
WORKSPACE_RUN=(uv run --package patchapi-control-api --with "httpx>=0.27,<0.29")
if [[ "${PATCHAPI_VERIFY_ISOLATED:-0}" != "1" ]] &&
  "${WORKSPACE_RUN[@]}" python -c "import fastapi, uvicorn, httpx, patchapi_control_api" \
    >/dev/null 2>&1; then
  echo "workspace environment (--package patchapi-control-api)"
  RUN=("${WORKSPACE_RUN[@]}")
  COMMAND="$COMMAND (workspace)"
else
  echo "NOTE: the workspace install of patchapi-control-api is not usable right now."
  echo "isolated environment"
  RUN=(
    uv run --no-project
    --with "fastapi>=0.115,<0.130"
    --with "uvicorn>=0.30,<0.40"
    --with "pydantic>=2.9,<3"
    --with "httpx>=0.27,<0.29"
    --with "pytest>=8.3,<9"
    --with "pytest-asyncio>=1.0,<2"
    --with "ruff>=0.14,<0.15"
  )
  COMMAND="$COMMAND (isolated)"
fi

step "ruff check"
"${RUN[@]}" ruff check services/control_api

step "ruff format --check"
"${RUN[@]}" ruff format --check services/control_api

step "pytest services/control_api"
"${RUN[@]}" pytest services/control_api -q

step "live server on an ephemeral port"
PORT="$("${RUN[@]}" python -c '
import socket

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
')"
echo "port $PORT"

SERVER_LOG="$(mktemp -t patchapi-control-api-XXXXXX)"
"${RUN[@]}" uvicorn patchapi_control_api.asgi:app \
  --host 127.0.0.1 --port "$PORT" --log-level warning >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

BASE="http://127.0.0.1:$PORT"
for _ in $(seq 1 80); do
  if curl -fsS "$BASE/healthz" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    cat "$SERVER_LOG" >&2
    fail "server exited before it began serving"
  fi
  sleep 0.25
done

probe() {
  # Echoes "<status> <body>" for one request; never aborts on a 4xx/5xx.
  curl -sS -o /tmp/patchapi_control_api_body -w '%{http_code}' "$1"
}

step "GET /healthz"
CODE="$(probe "$BASE/healthz")"
BODY="$(cat /tmp/patchapi_control_api_body)"
[[ "$CODE" == "200" ]] || fail "/healthz returned $CODE, expected 200"
printf '%s\n' "$BODY"
printf '%s' "$BODY" | "${RUN[@]}" python -c '
import json, sys

body = json.load(sys.stdin)
assert body["status"] == "ok", body
assert body["service"] == "patchapi-control-api", body
print("healthz JSON ok")
'

step "GET /openapi.json"
CODE="$(probe "$BASE/openapi.json")"
[[ "$CODE" == "200" ]] || fail "/openapi.json returned $CODE, expected 200"
"${RUN[@]}" python -c '
import json, sys

document = json.load(open("/tmp/patchapi_control_api_body"))
expected = {"/healthz", "/readyz", "/v1/provider-checks", "/v1/runs/{run_id}"}
served = set(document["paths"])
assert served == expected, f"served {sorted(served)}, expected {sorted(expected)}"
print("openapi paths:", ", ".join(sorted(served)))
'

step "GET /readyz fails closed while unwired"
CODE="$(probe "$BASE/readyz")"
[[ "$CODE" == "503" ]] || fail "/readyz returned $CODE, expected 503 with no ports wired"
"${RUN[@]}" python -c '
import json

body = json.load(open("/tmp/patchapi_control_api_body"))
assert body["status"] == "not_ready", body
missing = sorted(check["name"] for check in body["checks"] if not check["ready"])
assert missing == ["event_transport", "workflow_state_store"], missing
print("not ready:", ", ".join(missing))
'

step "GET /v1/runs/{run_id} fails closed while unwired"
CODE="$(probe "$BASE/v1/runs/run-000000000001")"
[[ "$CODE" == "503" ]] || fail "run read returned $CODE, expected 503 with no state store"
"${RUN[@]}" python -c '
import json

detail = json.load(open("/tmp/patchapi_control_api_body"))["detail"]
assert detail["error"] == "dependency_unavailable", detail
assert detail["dependency"] == "workflow_state_store", detail
print("run read fails closed:", detail["reason"])
'

step "unknown route is 404"
CODE="$(probe "$BASE/v1/not-a-route")"
[[ "$CODE" == "404" ]] || fail "unknown route returned $CODE, expected 404"

step "SIGTERM shutdown"
kill -TERM "$SERVER_PID"
EXIT_CODE=0
wait "$SERVER_PID" || EXIT_CODE=$?
# 0 is a graceful exit; 143 is 128+SIGTERM, which is how the `uv run` wrapper
# reports a child that was terminated by the signal it forwarded. Anything else
# means the server crashed on the way down.
case "$EXIT_CODE" in
  0 | 143) echo "exit code $EXIT_CODE" ;;
  *) fail "server exited with $EXIT_CODE after SIGTERM" ;;
esac
if grep -qE "Traceback|ERROR" "$SERVER_LOG"; then
  cat "$SERVER_LOG" >&2
  fail "server logged an error during its lifetime"
fi
if curl -fsS --max-time 2 "$BASE/healthz" >/dev/null 2>&1; then
  fail "server is still serving after SIGTERM"
fi
SERVER_PID=""
echo "server stopped and released port $PORT"

rm -f /tmp/patchapi_control_api_body

STATUS="PASS"
echo
echo "PASS: services/control_api verified"
