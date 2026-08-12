#!/usr/bin/env bash
# Dynamic verifier for agents/ (setup.md T-agents-adk).
#
# Three halves, and only the last one may be skipped:
#   compliance — Google ADK imports, and no other agent framework appears in
#                any runtime module of this tree. Never skipped.
#   offline    — the six specialists construct, every allowlist resolves to an
#                implemented tool, the guardrails refuse an out-of-allowlist
#                call, and the tools refuse to commit anything the deterministic
#                layer does not support. Never skipped.
#   live       — one real Change Intelligence turn on the pinned Google
#                deprecation fixture against Gemini 3.5 Flash on Vertex, which
#                must record a valid ChangeManifest. SKIP only when ADK or
#                credentials are genuinely absent; the smoke has no path that
#                prints PASS without a response from Google.
#
# Set PATCHAPI_REQUIRE_LIVE=1 to make an honest SKIP a failure (what CI and the
# aggregate verifier should do once credentials are provisioned).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_agents_adk.sh"
STATUS="FAIL"
NOTES="did not complete"

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-agents-adk","status":"%s","command":"%s","at":"%s","notes":"%s"}\n' \
    "$STATUS" "$COMMAND" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$NOTES" >>"$LEDGER"
}
trap record EXIT

step() { printf '\n== %s\n' "$1"; }

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv is not installed (see setup.md §3)"
  NOTES="uv missing"
  exit 1
fi

# Preferred path: the shared workspace environment. A workspace member in
# another tree that is mid-flight makes `uv sync` fail for every tree, which is
# not a defect in this one — fall back to an isolated environment built from
# this member's own pinned dependencies so it stays verifiable either way.
step "environment"
if uv sync --all-packages >/dev/null 2>&1; then
  echo "workspace environment"
  RUN=(uv run --all-packages)
  COMMAND="$COMMAND (workspace)"
else
  echo "NOTE: 'uv sync --all-packages' failed; another workspace member is likely incomplete."
  echo "isolated environment"
  RUN=(
    uv run --no-project
    --with "google-adk>=2.1,<3"
    --with "pydantic>=2.9,<3"
    --with "pytest>=8.3,<9"
    --with "pytest-asyncio>=1.0,<2"
    --with "ruff>=0.14,<0.15"
    --with "google-auth>=2.38,<3"
    --with "requests>=2.32,<3"
  )
  COMMAND="$COMMAND (isolated)"
fi

step "ADK imports and the pinned model"
"${RUN[@]}" python -c '
from agents.config import FLEET_NAME, FLEET_VERSION, REASONING_MODEL, SPECIALISTS
from agents.runtime import adk_unavailable_reason, adk_version

reason = adk_unavailable_reason()
assert reason is None, f"Google ADK is not importable: {reason}"
print("google-adk:    ", adk_version())
print("fleet:         ", FLEET_NAME, "v" + FLEET_VERSION)
print("specialists:   ", ", ".join(str(agent) for agent in SPECIALISTS))
print("reasoning pin: ", REASONING_MODEL)
assert len(SPECIALISTS) == 6, "roadmap section 8 names six specialists"
'

step "no other agent framework in the runtime path"
"${RUN[@]}" pytest agents/tests/test_framework_compliance.py -q

step "offline: fleet construction, allowlists, guardrails, tool contracts"
"${RUN[@]}" pytest agents -q

step "ruff check"
"${RUN[@]}" ruff check agents scripts/smoke_adk_orchestrator.py

step "ruff format --check"
"${RUN[@]}" ruff format --check agents scripts/smoke_adk_orchestrator.py

# The trace goes to a temp file rather than into demo/, which another tree owns.
# PATCHAPI_TRACE_OUT points it somewhere durable when a run's trace is wanted as
# a demo artifact.
TRACE_OUT="${PATCHAPI_TRACE_OUT:-$(mktemp -t patchapi-adk-trace)}"

step "live: Change Intelligence turn on Vertex gemini-3.5-flash"
set +e
"${RUN[@]}" python scripts/smoke_adk_orchestrator.py --trace-out "$TRACE_OUT"
LIVE_RC=$?
set -e

case "$LIVE_RC" in
  0)
    NOTES="compliance + offline PASS; live ChangeManifest turn PASS"
    ;;
  3)
    if [[ "${PATCHAPI_REQUIRE_LIVE:-0}" == "1" ]]; then
      echo "FAIL: live smoke skipped but PATCHAPI_REQUIRE_LIVE=1"
      NOTES="live smoke SKIP while required"
      exit 1
    fi
    NOTES="compliance + offline PASS; live smoke SKIP (ADK or credentials absent)"
    STATUS="SKIP"
    echo
    echo "SKIP: compliance and offline verification passed; the live turn was skipped."
    echo "      Provide .secrets/gcp-service-account.json and GCP_PROJECT to run it."
    exit 0
    ;;
  *)
    NOTES="live ADK smoke FAIL (exit $LIVE_RC)"
    exit "$LIVE_RC"
    ;;
esac

STATUS="PASS"
echo
echo "PASS: agents/ verified (ADK-only fleet + live Change Intelligence ChangeManifest)"
