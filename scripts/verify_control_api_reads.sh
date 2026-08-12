#!/usr/bin/env bash
# Dynamic verifier for the dashboard read path (packages/state + control_api).
#
# Proves the queries are real: it brings up the local Postgres, applies the
# migrations and the demo seed, serves the wired control plane, and asserts on
# rows that came out of the database. Nothing here is mocked — if the SQL is
# wrong, this fails.
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

step "GET /v1/changes returns the seeded provider change"
curl -fsS "$BASE/v1/changes" -o /tmp/patchapi_reads_body
uv run --quiet python -c '
import json

changes = json.load(open("/tmp/patchapi_reads_body"))["changes"]
assert changes, "no changes returned"
change = next(c for c in changes if c["change_id"] == "imagen4-retirement-2026-08-17")
assert change["recommended_replacement"] == "gemini-3.1-flash-image", change
assert len(change["affected_identifiers"]) == 3, change
# The seed captures no provider snapshot; the API must report that as null
# rather than as an empty string a dashboard could render as evidence.
assert change["source_sha256"] is None, change
assert change["affected_repositories"] >= 1, change
print("change:", change["change_id"], "->", change["recommended_replacement"])
'

step "GET /v1/repositories reports inventory findings with their commit"
curl -fsS "$BASE/v1/repositories?change_id=imagen4-retirement-2026-08-17" \
  -o /tmp/patchapi_reads_body
uv run --quiet python -c '
import json

body = json.load(open("/tmp/patchapi_reads_body"))
repositories = body["repositories"]
assert repositories, "no repositories returned"
egaki = next(r for r in repositories if r["repository"].endswith("/egaki"))
assert egaki["affected"] is True, egaki
assert egaki["usage_count"] > 0, egaki
assert egaki["indexed_sha"], "a finding with no commit is unfalsifiable"
assert egaki["usages"], egaki
layers = {u["detection_layer"] for u in egaki["usages"]}
assert "A_DETERMINISTIC" in layers, layers
print("affected:", egaki["repository"], egaki["usage_count"], "usages")
'

step "GET /v1/runs/{id}/detail assembles the evidence bundle"
RUN_ID="$(uv run --quiet python -c '
import json, urllib.request

with urllib.request.urlopen("'"$BASE"'/v1/runs") as response:
    runs = json.load(response)["runs"]
print(next(r["run_id"] for r in runs if r["state"] == "PR_CREATED"))
')"
curl -fsS "$BASE/v1/runs/${RUN_ID}/detail" -o /tmp/patchapi_reads_body
uv run --quiet python -c '
import json

body = json.load(open("/tmp/patchapi_reads_body"))
detail = body["detail"]
assert body["terminal"] is True, body
assert detail["transitions"], "no transition log"
policy = detail["policy"]
# Constraint 3, read back out of the database rather than asserted in prose.
assert policy["auto_merge"] is False, policy
assert policy["forbidden_globs"], policy
verification = detail["verification"]
assert verification["verdict"] == "PASS", verification
# Constraint 6: the verifier is not the agent that wrote the patch.
assert verification["verifier_agent"] != verification["patch_agent"], verification
assert detail["artifacts"], "no evidence recorded"
pull_request = detail["pull_request"]
assert pull_request["merged_by_patchapi"] is False, pull_request
attempts = {a["attempt_number"]: a for a in detail["attempts"]}
assert attempts[1]["test_exit_code"] == 1, attempts[1]
assert attempts[2]["test_exit_code"] == 0, attempts[2]
print("run:", detail["summary"]["run_id"], "->", detail["summary"]["state"])
print("verification:", verification["verdict"], "by", verification["verifier_agent"])
'

step "GET /v1/fleet surfaces refused actions"
curl -fsS "$BASE/v1/fleet" -o /tmp/patchapi_reads_body
uv run --quiet python -c '
import json

body = json.load(open("/tmp/patchapi_reads_body"))
denials = body["denials"]
assert denials, "no denials returned; the governance evidence is missing"
actions = {d["action"] for d in denials}
assert "github_tools.merge_pull_request" in actions, actions
for denial in denials:
    assert denial["outcome"] == "DENIED", denial
    # The schema requires a reason on every denial; the API must carry it.
    assert denial["reason"], denial
print("denials:", ", ".join(sorted(actions)))
'

step "an unknown run is 404, not an empty bundle"
CODE="$(curl -s -o /dev/null -w '%{http_code}' \
  "$BASE/v1/runs/00000000-0000-4000-8000-000000000000/detail")"
[[ "$CODE" == "404" ]] || fail "unknown run returned $CODE, expected 404"

rm -f /tmp/patchapi_reads_body

echo
echo "PASS: the dashboard read path serves real rows from authoritative Postgres"
