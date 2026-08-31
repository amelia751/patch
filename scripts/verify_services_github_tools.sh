#!/usr/bin/env bash
# Dynamic verifier for services/github_tools (setup.md T-services-github_tools).
#
# Lints and unit-tests the tree, boots the real ASGI application on an ephemeral
# port, and proves over HTTP that the narrow capability surface behaves:
#
#   * the catalog lists exactly the roadmap §7.3 read and write operations,
#   * every "explicitly absent" operation returns a structured 403,
#   * an unrecognised caller is refused, and a read-only agent cannot write,
#   * the MCP JSON-RPC endpoint publishes a per-identity tool list that names no
#     forbidden operation, and refuses a call through the same gates,
#   * with no GitHub App configured every invocation fails closed with a 503
#     that names the missing dependency.
#
# The live leg — get_repository_metadata against the demo fork — runs only when
# GitHub App credentials are present. Absent, it prints an explicit SKIP; it is
# never faked. Exits non-zero on any failure and records the outcome in the
# shared setup ledger.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_services_github_tools.sh"
STATUS="FAIL"
# Records which optional legs did not run, so a PASS is never mistaken for
# "the live GitHub App path was exercised".
NOTE=""
SERVER_PID=""
SERVER_LOG=""
BODY_FILE="$(mktemp -t patchapi-github-tools-body-XXXXXX)"

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-services-github_tools","status":"%s","command":"%s","note":"%s","at":"%s"}\n' \
    "$STATUS" "$COMMAND" "$NOTE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LEDGER"
}

teardown() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  [[ -n "$SERVER_LOG" ]] && rm -f "$SERVER_LOG"
  rm -f "$BODY_FILE"
  record
}
trap teardown EXIT

step() { printf '\n== %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

command -v uv >/dev/null 2>&1 || fail "uv is not installed (see setup.md §3)"
command -v curl >/dev/null 2>&1 || fail "curl is not installed"

# The service imports the shared capability vocabulary from the checkout rather
# than from an installed wheel, so the probe exercises the source this tree and
# packages/github own.
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/services/github_tools/src"

# Preferred path: this package installed from the workspace, which also proves
# it is a real workspace member. Scoped with `--package` so a sibling tree that
# is mid-flight cannot fail this tree's verification; if even the scoped install
# is unusable, fall back to an isolated environment built from this package's
# own pinned dependencies.
#
# Set PATCHAPI_VERIFY_ISOLATED=1 to exercise the fallback deliberately.
step "environment"
WORKSPACE_RUN=(uv run --package patchapi-github-tools)
if [[ "${PATCHAPI_VERIFY_ISOLATED:-0}" != "1" ]] &&
  "${WORKSPACE_RUN[@]}" python -c \
    "import fastapi, httpx, uvicorn, cryptography, patchapi_github_tools" >/dev/null 2>&1; then
  echo "workspace environment (--package patchapi-github-tools)"
  RUN=("${WORKSPACE_RUN[@]}")
  COMMAND="$COMMAND (workspace)"
else
  echo "NOTE: the workspace install of patchapi-github-tools is not usable right now."
  echo "isolated environment"
  RUN=(
    uv run --no-project
    --with "cryptography>=43,<51"
    --with "fastapi>=0.115,<0.130"
    --with "httpx>=0.27,<0.29"
    --with "pydantic>=2.9,<3"
    --with "uvicorn>=0.30,<0.40"
    --with "pytest>=8.3,<9"
    --with "pytest-asyncio>=1.0,<2"
    --with "ruff>=0.14,<0.15"
  )
  COMMAND="$COMMAND (isolated)"
fi

step "ruff check"
"${RUN[@]}" ruff check services/github_tools

step "ruff format --check"
"${RUN[@]}" ruff format --check services/github_tools

step "pytest services/github_tools"
"${RUN[@]}" pytest services/github_tools -q

step "live server on an ephemeral port"
PORT="$("${RUN[@]}" python -c '
import socket

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
')"
echo "port $PORT"

SERVER_LOG="$(mktemp -t patchapi-github-tools-XXXXXX)"
# Started with no App credentials on purpose: this leg proves the fail-closed
# posture. The live leg below builds its own client from real credentials.
env -u GITHUB_APP_ID -u GITHUB_APP_INSTALLATION_ID \
  -u GITHUB_APP_PRIVATE_KEY_PATH -u GITHUB_APP_PRIVATE_KEY_SECRET \
  "${RUN[@]}" uvicorn patchapi_github_tools.asgi:app \
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
  # Echoes the status code for one request and leaves the body in $BODY_FILE.
  local method="$1" url="$2"
  shift 2
  curl -sS -X "$method" -o "$BODY_FILE" -w '%{http_code}' "$url" "$@"
}

step "GET /healthz"
CODE="$(probe GET "$BASE/healthz")"
[[ "$CODE" == "200" ]] || fail "/healthz returned $CODE, expected 200"
"${RUN[@]}" python -c '
import json

body = json.load(open("'"$BODY_FILE"'"))
assert body["status"] == "ok", body
assert body["service"] == "patchapi-github-tools", body
print("healthz JSON ok")
'

step "GET /readyz fails closed with no GitHub App"
CODE="$(probe GET "$BASE/readyz")"
[[ "$CODE" == "503" ]] || fail "/readyz returned $CODE, expected 503 with no App configured"
"${RUN[@]}" python -c '
import json

body = json.load(open("'"$BODY_FILE"'"))
assert body["status"] == "not_ready", body
check = body["checks"][0]
assert check["name"] == "github_app_installation" and not check["ready"], body
print("not ready:", check["reason"])
'

step "GET /v1/capabilities is exactly the roadmap §7.3 surface"
CODE="$(probe GET "$BASE/v1/capabilities")"
[[ "$CODE" == "200" ]] || fail "capability catalog returned $CODE, expected 200"
"${RUN[@]}" python -c '
import json

body = json.load(open("'"$BODY_FILE"'"))
exposed = {entry["name"] for entry in body["exposed"]}
expected = {
    "get_repository_metadata", "get_file", "list_tree", "get_commit",
    "get_pull_request", "get_checks", "create_patch_branch",
    "commit_verified_patch", "open_pull_request", "add_pr_comment",
}
assert exposed == expected, sorted(exposed ^ expected)
never = set(body["never_exposed"])
assert {"merge_pull_request", "change_branch_protection", "modify_actions_secrets",
        "modify_repository_admin_settings", "delete_repository"} <= never, sorted(never)
assert not exposed & never, sorted(exposed & never)
assert body["grants"]["patchapi.change_intelligence"] == [], body["grants"]
print("exposed:", len(exposed), "never exposed:", len(never))
'

step "forbidden capabilities return a structured 403"
FORBIDDEN=(
  merge_pull_request
  squash_merge_pull_request
  rebase_merge_pull_request
  change_branch_protection
  modify_actions_secrets
  modify_repository_admin_settings
  delete_repository
  add_collaborator
  update_codeowners
  approve_pull_request
  dismiss_review
  delete_branch_protection_rule
)
for capability in "${FORBIDDEN[@]}"; do
  CODE="$(probe POST "$BASE/v1/capabilities/$capability" \
    -H 'Content-Type: application/json' \
    -H 'X-PatchAPI-Agent: patchapi.pr' \
    -d '{"repo":"amelia751/storygen"}')"
  [[ "$CODE" == "403" ]] || fail "$capability returned $CODE, expected 403"
  "${RUN[@]}" python -c '
import json, sys

detail = json.load(open("'"$BODY_FILE"'"))["detail"]
assert detail["error"] == "forbidden_capability", detail
assert detail["capability"] == sys.argv[1], detail
assert "stops at the pull request" in detail["reason"], detail
' "$capability"
  echo "403 $capability"
done

step "unknown capability is a structured 404"
CODE="$(probe POST "$BASE/v1/capabilities/rm_minus_rf" \
  -H 'Content-Type: application/json' -H 'X-PatchAPI-Agent: patchapi.pr' -d '{}')"
[[ "$CODE" == "404" ]] || fail "unknown capability returned $CODE, expected 404"
"${RUN[@]}" python -c '
import json

detail = json.load(open("'"$BODY_FILE"'"))["detail"]
assert detail["error"] == "unknown_capability", detail
print("unknown capability refused")
'

step "unrecognised caller is refused"
CODE="$(probe POST "$BASE/v1/capabilities/get_repository_metadata" \
  -H 'Content-Type: application/json' -H 'X-PatchAPI-Agent: attacker.agent' \
  -d '{"repo":"amelia751/storygen"}')"
[[ "$CODE" == "401" ]] || fail "unknown agent returned $CODE, expected 401"

step "read-only agent cannot reach a write capability"
CODE="$(probe POST "$BASE/v1/capabilities/open_pull_request" \
  -H 'Content-Type: application/json' -H 'X-PatchAPI-Agent: patchapi.impact' \
  -d '{"repo":"amelia751/storygen"}')"
[[ "$CODE" == "403" ]] || fail "ungranted write returned $CODE, expected 403"
"${RUN[@]}" python -c '
import json

detail = json.load(open("'"$BODY_FILE"'"))["detail"]
assert detail["error"] == "capability_not_granted", detail
assert "open_pull_request" not in detail["granted_capabilities"], detail
print("write refused for", detail["agent"])
'

step "a granted capability fails closed without credentials"
CODE="$(probe POST "$BASE/v1/capabilities/get_repository_metadata" \
  -H 'Content-Type: application/json' -H 'X-PatchAPI-Agent: patchapi.impact' \
  -d '{"repo":"amelia751/storygen"}')"
[[ "$CODE" == "503" ]] || fail "unwired invocation returned $CODE, expected 503"
"${RUN[@]}" python -c '
import json

detail = json.load(open("'"$BODY_FILE"'"))["detail"]
assert detail["error"] == "dependency_unavailable", detail
assert detail["dependency"] == "github_app_installation", detail
assert "no GitHub call was attempted" in detail["reason"], detail
print("fails closed:", detail["reason"])
'

step "POST /mcp initialize advertises the MCP server identity"
CODE="$(probe POST "$BASE/mcp" \
  -H 'Content-Type: application/json' -H 'X-PatchAPI-Agent: patchapi.pr' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}')"
[[ "$CODE" == "200" ]] || fail "mcp initialize returned $CODE, expected 200"
"${RUN[@]}" python -c '
import json

from patchapi_github_tools.config import MCP_PROTOCOL_VERSION, SERVICE_NAME, SERVICE_VERSION

body = json.load(open("'"$BODY_FILE"'"))
assert body["jsonrpc"] == "2.0" and body["id"] == 1, body
result = body["result"]
assert result["protocolVersion"] == MCP_PROTOCOL_VERSION, result
assert result["serverInfo"] == {"name": SERVICE_NAME, "version": SERVICE_VERSION}, result
assert "stops at the pull request" in result["instructions"], result
print("mcp", result["protocolVersion"], result["serverInfo"])
'

step "POST /mcp tools/list is per-identity and omits every forbidden operation"
for identity in patchapi.pr patchapi.impact patchapi.change_intelligence; do
  CODE="$(probe POST "$BASE/mcp" \
    -H 'Content-Type: application/json' -H "X-PatchAPI-Agent: $identity" \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}')"
  [[ "$CODE" == "200" ]] || fail "mcp tools/list returned $CODE for $identity, expected 200"
  "${RUN[@]}" python -c '
import json, sys

from packages.github import FORBIDDEN_CAPABILITIES

identity = sys.argv[1]
tools = json.load(open("'"$BODY_FILE"'"))["result"]["tools"]
names = {tool["name"] for tool in tools}
assert not names & set(FORBIDDEN_CAPABILITIES), sorted(names & set(FORBIDDEN_CAPABILITIES))
expected = {
    "patchapi.pr": 10,
    "patchapi.impact": 6,
    # Roadmap §8.1: reads untrusted provider material, holds no grant at all.
    "patchapi.change_intelligence": 0,
}[identity]
assert len(names) == expected, (identity, sorted(names))
for tool in tools:
    annotations = tool["annotations"]
    assert annotations["destructiveHint"] is False, tool["name"]
    assert "$ref" not in json.dumps(tool["inputSchema"]), tool["name"]
reads = {tool["name"] for tool in tools if tool["annotations"]["readOnlyHint"]}
print(f"{identity}: {len(names)} tools, {len(reads)} read-only")
' "$identity"
done

step "POST /mcp tools/call is refused by the same gates as the REST route"
CODE="$(probe POST "$BASE/mcp" \
  -H 'Content-Type: application/json' -H 'X-PatchAPI-Agent: patchapi.pr' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"merge_pull_request"}}')"
[[ "$CODE" == "200" ]] || fail "mcp refusal returned $CODE, expected a 200 JSON-RPC error"
"${RUN[@]}" python -c '
import json

error = json.load(open("'"$BODY_FILE"'"))["error"]
assert error["code"] == -32001, error
assert error["data"]["error"] == "forbidden_capability", error
assert "stops at the pull request" in error["data"]["reason"], error
print("mcp forbidden:", error["code"], error["data"]["capability"])
'

CODE="$(probe POST "$BASE/mcp" \
  -H 'Content-Type: application/json' -H 'X-PatchAPI-Agent: patchapi.impact' \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"open_pull_request","arguments":{"repo":"amelia751/storygen"}}}')"
[[ "$CODE" == "200" ]] || fail "mcp ungranted write returned $CODE, expected a 200 JSON-RPC error"
"${RUN[@]}" python -c '
import json

error = json.load(open("'"$BODY_FILE"'"))["error"]
assert error["code"] == -32002, error
assert error["data"]["error"] == "capability_not_granted", error
assert "open_pull_request" not in error["data"]["granted_capabilities"], error
print("mcp not granted:", error["code"], error["data"]["agent"])
'

CODE="$(probe POST "$BASE/mcp" \
  -H 'Content-Type: application/json' -H 'X-PatchAPI-Agent: attacker.agent' \
  -d '{"jsonrpc":"2.0","id":5,"method":"tools/list"}')"
[[ "$CODE" == "401" ]] || fail "mcp unknown agent returned $CODE, expected 401"

CODE="$(probe POST "$BASE/mcp" \
  -H 'Content-Type: application/json' -H 'X-PatchAPI-Agent: patchapi.pr' \
  -d '{"jsonrpc":')"
[[ "$CODE" == "200" ]] || fail "mcp malformed envelope returned $CODE, expected a 200 JSON-RPC error"
"${RUN[@]}" python -c '
import json

error = json.load(open("'"$BODY_FILE"'"))["error"]
assert error["code"] == -32700, error
print("mcp parse error:", error["code"])
'

step "OpenAPI describes no merge, admin, secret, or protection route"
CODE="$(probe GET "$BASE/openapi.json")"
[[ "$CODE" == "200" ]] || fail "/openapi.json returned $CODE, expected 200"
"${RUN[@]}" python -c '
import json

document = json.load(open("'"$BODY_FILE"'"))
paths = set(document["paths"])
expected = {
    "/healthz", "/readyz", "/mcp", "/v1/capabilities", "/v1/capabilities/{capability_name}",
}
assert paths == expected, sorted(paths ^ expected)
serialized = json.dumps(document["paths"])
for banned in ("/merge", "/protection", "/admin", "/secrets"):
    assert banned not in serialized, banned
print("openapi paths:", ", ".join(sorted(paths)))
'

step "SIGTERM shutdown"
kill -TERM "$SERVER_PID"
EXIT_CODE=0
wait "$SERVER_PID" || EXIT_CODE=$?
# 0 is a graceful exit; 143 is 128+SIGTERM, which is how the `uv run` wrapper
# reports a child terminated by the signal it forwarded.
case "$EXIT_CODE" in
  0 | 143) echo "exit code $EXIT_CODE" ;;
  *) fail "server exited with $EXIT_CODE after SIGTERM" ;;
esac
if grep -qE "Traceback|ERROR" "$SERVER_LOG"; then
  cat "$SERVER_LOG" >&2
  fail "server logged an error during its lifetime"
fi
SERVER_PID=""

step "live GitHub App read"
DEMO_REPO="${PATCHAPI_DEMO_REPO:-amelia751/storygen}"
if [[ -z "${GITHUB_APP_ID:-}" || -z "${GITHUB_APP_INSTALLATION_ID:-}" ]] ||
  [[ -z "${GITHUB_APP_PRIVATE_KEY_PATH:-}" && -z "${GITHUB_APP_PRIVATE_KEY_SECRET:-}" ]]; then
  echo "SKIP: GitHub App not configured."
  echo "      Set GITHUB_APP_ID, GITHUB_APP_INSTALLATION_ID, and one of"
  echo "      GITHUB_APP_PRIVATE_KEY_PATH (a file under .secrets/) or"
  echo "      GITHUB_APP_PRIVATE_KEY_SECRET (a Secret Manager resource name)."
  echo "      setup.md §8 records the App as deferred to a later batch."
  STATUS="PASS"
  NOTE="SKIP: live GitHub App read (App not configured)"
else
  "${RUN[@]}" python - "$DEMO_REPO" <<'PY'
import asyncio
import sys

from patchapi_github_tools.models import GetRepositoryMetadataArgs
from patchapi_github_tools.operations import get_repository_metadata
from patchapi_github_tools.wiring import build_github_client


async def main() -> None:
    client = build_github_client()
    if client is None:  # guarded by the shell above
        raise SystemExit("FAIL: credentials disappeared between checks")
    result = await get_repository_metadata(
        client, GetRepositoryMetadataArgs(repo=sys.argv[1])
    )
    assert result["full_name"].lower() == sys.argv[1].lower(), result
    print("live read ok:", result["full_name"], "default branch", result["default_branch"])


asyncio.run(main())
PY
  STATUS="PASS"
fi

if [[ "$STATUS" == FAIL ]]; then
  fail "reached the end without a PASS status"
fi

echo
echo "PASS: services/github_tools verified${NOTE:+ — $NOTE}"
exit 0
