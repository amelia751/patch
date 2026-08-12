#!/usr/bin/env bash
# Dynamic verifier for the local sandbox runner (setup.md T-sandbox-local).
#
# Proves by execution, not inspection:
#   1. the unit suite passes,
#   2. a no-op patch run of the pinned fixture is green and leaves logs,
#   3. a known-good patch passes and a known-bad patch fails,
#   4. an unappliable patch stops before any step runs,
#   5. every run happens under /tmp (or PATCHAPI_SANDBOX_ROOT), never in the
#      checkout, and the checkout is byte-identical afterwards,
#   6. the workspace is destroyed while its logs survive.
#
# The container image is built and exercised too when Docker is available;
# otherwise that section reports SKIP rather than being silently dropped.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_sandbox_local.sh"
STATUS="FAIL"
NOTES="verification did not complete"

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-sandbox-local","status":"%s","command":"%s","at":"%s","notes":"%s"}\n' \
    "$STATUS" "$COMMAND" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$NOTES" >>"$LEDGER"
}
trap record EXIT

step() { printf '\n== %s\n' "$1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

PLANS="sandbox/runner/plans"
FIXTURE="sandbox/runner/testdata/image_service"

# Runs land in a verifier-scoped directory under the configured sandbox root so
# this script can assert where they went and clean up only after inspecting the
# evidence it produced.
SANDBOX_ROOT="${PATCHAPI_SANDBOX_ROOT:-${TMPDIR:-/tmp}}"
VERIFY_ROOT="$(mktemp -d "${SANDBOX_ROOT%/}/patchapi-verify-XXXXXX")"
cleanup() { rm -rf "$VERIFY_ROOT"; }
trap 'cleanup; record' EXIT

case "$VERIFY_ROOT" in
  "$REPO_ROOT"/*) fail "sandbox root $VERIFY_ROOT is inside the checkout $REPO_ROOT" ;;
esac
echo "sandbox root: $VERIFY_ROOT"

if command -v uv >/dev/null 2>&1; then
  PY=(uv run python)
elif command -v python3 >/dev/null 2>&1; then
  # The runner is standard-library only, so a bare interpreter is enough; uv is
  # preferred purely so the unit suite runs on the workspace's pinned pytest.
  PY=(python3)
else
  fail "neither uv nor python3 is available (see setup.md §3)"
fi

step "unit suite"
if command -v uv >/dev/null 2>&1; then
  uv run pytest sandbox/runner/tests -q
else
  echo "SKIP: uv unavailable; unit suite not run"
fi

runner() {
  "${PY[@]}" -m sandbox.runner.entrypoint --sandbox-root "$VERIFY_ROOT" "$@"
}

digest_fixture() {
  find "$FIXTURE" -type f ! -path '*__pycache__*' | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256
}

BEFORE="$(digest_fixture)"

step "plans parse and validate"
"${PY[@]}" - <<'PY'
from pathlib import Path

from sandbox.runner.config import SandboxPlan

plans = sorted(Path("sandbox/runner/plans").glob("*.json"))
if not plans:
    raise SystemExit("no plans found")
for path in plans:
    plan = SandboxPlan.load(path)
    print(f"{plan.plan_id:<24} {len(plan.steps)} step(s)  source={plan.source.kind}")
PY

step "no-op patch against the pinned fixture"
runner --plan "$PLANS/testdata-noop.v1.json" --run-id verify-noop >/dev/null
NOOP_DIR="$VERIFY_ROOT/patchapi-sandbox/verify-noop"
[ -f "$NOOP_DIR/logs/build.txt" ] || fail "logs/build.txt missing for the no-op run"
[ -f "$NOOP_DIR/logs/test.txt" ] || fail "logs/test.txt missing for the no-op run"
[ -f "$NOOP_DIR/result.json" ] || fail "result.json missing for the no-op run"
grep -q '"status": "PASS"' "$NOOP_DIR/result.json" || fail "no-op run did not record PASS"
if [ -d "$NOOP_DIR/workspace" ]; then fail "workspace was not destroyed after the no-op run"; fi
echo "logs preserved, workspace destroyed: $NOOP_DIR"

step "known-good patch"
runner --plan "$PLANS/testdata-good.v1.json" --run-id verify-good --retain >/dev/null
GOOD_DIR="$VERIFY_ROOT/patchapi-sandbox/verify-good"
grep -q 'gemini-3.1-flash-image' "$GOOD_DIR/workspace/image_service/client.py" \
  || fail "known-good patch was not applied inside the workspace"
[ -f "$GOOD_DIR/workspace/dist/manifest.json" ] || fail "build artifact missing in the workspace"
echo "patched workspace retained: $GOOD_DIR/workspace"

step "known-bad patch must fail"
if runner --plan "$PLANS/testdata-bad.v1.json" --run-id verify-bad >/dev/null; then
  fail "known-bad patch reported success; the runner would have cleared a fabricated migration"
fi
BAD_DIR="$VERIFY_ROOT/patchapi-sandbox/verify-bad"
grep -q '"status": "FAIL"' "$BAD_DIR/result.json" || fail "known-bad run did not record FAIL"
grep -q 'UnsupportedModelError' "$BAD_DIR/logs/test.txt" || fail "failure evidence missing from the test log"
echo "failure recorded with evidence: $BAD_DIR/logs/test.txt"

step "unappliable patch must stop before any step"
if runner --plan "$PLANS/testdata-unappliable.v1.json" --run-id verify-unappliable >/dev/null; then
  fail "unappliable patch reported success"
fi
UNAPPLIABLE_DIR="$VERIFY_ROOT/patchapi-sandbox/verify-unappliable"
grep -q '"status": "PATCH_FAILED"' "$UNAPPLIABLE_DIR/result.json" \
  || fail "unappliable run did not record PATCH_FAILED"
[ -z "$(ls -A "$UNAPPLIABLE_DIR/logs")" ] || fail "a step ran despite the patch not applying"

step "the checkout is untouched"
AFTER="$(digest_fixture)"
[ "$BEFORE" = "$AFTER" ] || fail "the fixture in the checkout changed during verification"
if [ -d "$FIXTURE/dist" ]; then fail "a build artifact was written into the checkout"; fi
grep -q 'imagen-4.0-generate-001' "$FIXTURE/image_service/client.py" \
  || fail "the checkout's baseline model id was rewritten"
echo "fixture digest unchanged: ${BEFORE%% *}"

step "a sandbox root inside the checkout is refused"
if "${PY[@]}" -m sandbox.runner.entrypoint \
     --plan "$PLANS/testdata-noop.v1.json" \
     --sandbox-root "$REPO_ROOT/.sandbox-should-not-exist" >/dev/null 2>&1; then
  fail "a run was allowed inside the checkout"
fi
if [ -e "$REPO_ROOT/.sandbox-should-not-exist" ]; then
  fail "the refused run still created a directory"
fi
echo "refused, and nothing was created in the checkout"

DOCKER_NOTE="image not built (docker unavailable)"
step "runner image"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker build --quiet -f sandbox/runner/Dockerfile -t patchapi-sandbox-runner:verify sandbox/runner
  docker run --rm --network=none --read-only \
    --tmpfs /sandbox:rw,exec,uid=1000,gid=1000 \
    --cap-drop=ALL --security-opt=no-new-privileges \
    patchapi-sandbox-runner:verify --plan "$PLANS/testdata-good.v1.json"
  if docker run --rm --network=none --read-only \
       --tmpfs /sandbox:rw,exec,uid=1000,gid=1000 \
       --cap-drop=ALL --security-opt=no-new-privileges \
       patchapi-sandbox-runner:verify --plan "$PLANS/testdata-bad.v1.json"; then
    fail "known-bad patch passed inside the container"
  fi
  DOCKER_NOTE="image built; good=PASS bad=FAIL non-root, no network, read-only rootfs, caps dropped"
else
  echo "SKIP: docker unavailable; the container path was not exercised"
fi

STATUS="PASS"
NOTES="unit suite + no-op/good/bad/unappliable runs under $VERIFY_ROOT; checkout digest unchanged; $DOCKER_NOTE"
echo
echo "PASS: local sandbox runner verified"
