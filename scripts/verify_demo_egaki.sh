#!/usr/bin/env bash
# Dynamic verifier for the pinned Egaki demo baseline (setup.md T-demo-baseline).
#
# Proves, against the SHA pinned in demo/egaki/baseline.json:
#   1. the checkout really is that SHA,
#   2. the Imagen 4 identifiers PatchAPI must detect are present in it,
#   3. the deterministic build/test gates the sandbox will run actually pass,
#   4. (opt-in) a live Gemini 3.1 Flash Image call succeeds.
#
# Step 4 is opt-in because the baseline CLI predates the migration; it exists so
# a human can discharge the roadmap Phase 0 exit criterion without hand-running
# credentials. Missing credentials SKIP, never PASS.
#
# Usage:
#   scripts/verify_demo_egaki.sh                 # steps 1-3, step 4 SKIP
#   PATCHAPI_LIVE_IMAGE=1 scripts/verify_demo_egaki.sh
#
# Exit 0 = PASS (SKIPs allowed on the live step only). Non-zero = FAIL.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE="${REPO_ROOT}/demo/egaki/baseline.json"
FIXTURE="${REPO_ROOT}/demo/fixtures/google-imagen4-deprecation.json"
CHECKOUT="${REPO_ROOT}/demo/egaki/checkout"
ARTIFACTS="${REPO_ROOT}/demo/egaki/artifacts"
LEDGER="${REPO_ROOT}/demo/setup-ledger.ndjson"
TASK_ID="T-demo-baseline"

FAILED=0
SKIPS=()
STEPS=()
LAST_COMMAND="(none)"

log()  { printf '\n=== %s\n' "$*"; }
pass() { printf 'PASS: %s\n' "$*"; STEPS+=("PASS|$*"); }
skip() { printf 'SKIP: %s\n' "$*"; SKIPS+=("$*"); STEPS+=("SKIP|$*"); }
fail() { printf 'FAIL: %s\n' "$*" >&2; FAILED=1; STEPS+=("FAIL|$*"); }

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# One NDJSON line per run, per setup.md §1 "Shared ledger". Each gate's own
# outcome is recorded: a run that PASSes overall while skipping the live call is
# materially different evidence from one that passed it, and the ledger is where
# that distinction has to survive.
write_ledger() {
  local status="$1"
  mkdir -p "$(dirname "${LEDGER}")"
  python3 - "$LEDGER" "$TASK_ID" "$status" "$LAST_COMMAND" "$(now_utc)" "${STEPS[@]+"${STEPS[@]}"}" <<'PY'
import json, sys
ledger, task, status, command, at = sys.argv[1:6]
steps = [
    {"status": s.split("|", 1)[0], "detail": s.split("|", 1)[1]}
    for s in sys.argv[6:]
]
with open(ledger, "a", encoding="utf-8") as fh:
    fh.write(json.dumps({
        "task": task, "status": status,
        "command": "scripts/verify_demo_egaki.sh",
        "last_step": command, "steps": steps, "at": at,
    }) + "\n")
PY
}

finish() {
  local status="PASS"
  [[ "${FAILED}" -ne 0 ]] && status="FAIL"
  write_ledger "${status}"
  log "RESULT: ${status}"
  if [[ ${#SKIPS[@]} -gt 0 ]]; then
    printf 'skipped:\n'
    printf '  - %s\n' "${SKIPS[@]}"
  fi
  exit "${FAILED}"
}
trap finish EXIT

# --- prerequisites -----------------------------------------------------------

for tool in git pnpm python3 node; do
  command -v "${tool}" >/dev/null 2>&1 || { fail "missing required tool: ${tool}"; exit 1; }
done

[[ -f "${BASELINE}" ]] || { fail "missing ${BASELINE}"; exit 1; }
[[ -f "${FIXTURE}" ]]  || { fail "missing ${FIXTURE}"; exit 1; }

read_json() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2"; }

FORK_URL="$(read_json "${BASELINE}" fork)"
PINNED_SHA="$(read_json "${BASELINE}" fork_base_sha)"
CLONE_URL="${FORK_URL%.git}.git"

mkdir -p "${ARTIFACTS}"

# --- step 1: checkout is exactly the pinned SHA ------------------------------

log "step 1/4 — materialize ${FORK_URL} @ ${PINNED_SHA}"
LAST_COMMAND="git checkout ${PINNED_SHA}"

if [[ ! -d "${CHECKOUT}/.git" ]]; then
  rm -rf "${CHECKOUT}"
  git clone --filter=blob:none --no-checkout "${CLONE_URL}" "${CHECKOUT}" || { fail "clone failed"; exit 1; }
fi

if ! git -C "${CHECKOUT}" cat-file -e "${PINNED_SHA}^{commit}" 2>/dev/null; then
  git -C "${CHECKOUT}" fetch --filter=blob:none origin "${PINNED_SHA}" || \
    git -C "${CHECKOUT}" fetch --filter=blob:none origin || { fail "fetch failed"; exit 1; }
fi

git -C "${CHECKOUT}" -c advice.detachedHead=false checkout --force "${PINNED_SHA}" >/dev/null 2>&1 || {
  fail "cannot check out ${PINNED_SHA}"; exit 1; }

HEAD_SHA="$(git -C "${CHECKOUT}" rev-parse HEAD)"
if [[ "${HEAD_SHA}" != "${PINNED_SHA}" ]]; then
  fail "checkout HEAD ${HEAD_SHA} != pinned ${PINNED_SHA}"
  exit 1
fi
pass "checkout at pinned SHA ${HEAD_SHA}"

# --- step 2: the pinned SHA still exposes the Imagen 4 identifiers ------------

log "step 2/4 — confirm Imagen 4 identifiers at the pinned SHA"
LAST_COMMAND="rg -n imagen-4.0-generate-001 demo/egaki/checkout"

if command -v rg >/dev/null 2>&1; then
  SEARCH() { rg --no-heading --line-number --fixed-strings "$1" "${CHECKOUT}" --glob '!.git' --glob '!node_modules'; }
else
  SEARCH() { grep -rn --binary-files=without-match --exclude-dir=.git --exclude-dir=node_modules -F "$1" "${CHECKOUT}"; }
fi

# The required identifier gates the demo; the rest of the fixture family is
# reported for the expected-findings inventory but is not individually required.
REQUIRED_ID="imagen-4.0-generate-001"
if ! SEARCH "${REQUIRED_ID}" >"${ARTIFACTS}/imagen-scan.txt" 2>/dev/null; then
  fail "${REQUIRED_ID} not found at ${PINNED_SHA} — the baseline no longer demonstrates the exposure"
  exit 1
fi
REQUIRED_HITS="$(wc -l <"${ARTIFACTS}/imagen-scan.txt" | tr -d ' ')"
pass "${REQUIRED_ID}: ${REQUIRED_HITS} hits (see demo/egaki/artifacts/imagen-scan.txt)"

# Per-identifier inventory for the Impact Agent's expected findings.
python3 - "${FIXTURE}" "${CHECKOUT}" "${ARTIFACTS}/imagen-inventory.json" <<'PY'
import json, subprocess, sys, pathlib
fixture, checkout, out = sys.argv[1:4]
ids = json.load(open(fixture))["affected_identifiers"]
inventory = {}
for ident in ids:
    proc = subprocess.run(
        ["grep", "-rn", "--binary-files=without-match",
         "--exclude-dir=.git", "--exclude-dir=node_modules", "-F", ident, checkout],
        capture_output=True, text=True,
    )
    hits = []
    for line in proc.stdout.splitlines():
        path, _, rest = line.partition(":")
        lineno, _, _ = rest.partition(":")
        hits.append({"file": str(pathlib.Path(path).relative_to(checkout)), "line": int(lineno)})
    inventory[ident] = hits
json.dump(inventory, open(out, "w"), indent=2, sort_keys=True)
for ident, hits in sorted(inventory.items()):
    print(f"  {ident}: {len(hits)} hit(s)")
PY

# --- step 3: deterministic build and test gates ------------------------------

log "step 3/4 — pnpm install / build / test"

LAST_COMMAND="pnpm install --frozen-lockfile"
if ! (cd "${CHECKOUT}" && pnpm install --frozen-lockfile 2>&1 | tail -25); then
  printf 'note: --frozen-lockfile failed, retrying without it\n'
  LAST_COMMAND="pnpm install"
  if ! (cd "${CHECKOUT}" && pnpm install 2>&1 | tail -25); then
    fail "pnpm install failed"
    exit 1
  fi
  skip "pnpm install --frozen-lockfile rejected the pinned lockfile; used plain 'pnpm install'"
fi
pass "${LAST_COMMAND}"

LAST_COMMAND="pnpm --dir cli build"
if ! (cd "${CHECKOUT}" && pnpm --dir cli build 2>&1 | tail -30); then
  fail "pnpm --dir cli build failed"
  exit 1
fi
pass "pnpm --dir cli build"

LAST_COMMAND="pnpm --dir cli test"
if ! (cd "${CHECKOUT}" && pnpm --dir cli test 2>&1 | tail -40); then
  fail "pnpm --dir cli test failed"
  exit 1
fi
pass "pnpm --dir cli test"

# --- step 4: optional live replacement-model call ----------------------------

# Deliberately NOT ${PATCHAPI_IMAGE_MODEL}: that env var pins the *provider*
# model id ("gemini-3.1-flash-image"), which is not a valid id in Egaki's model
# catalog at the pinned SHA. Conflating the two is the exact string-replace
# mistake this demo exists to disprove — see demo/egaki/expected-findings.yaml.
EGAKI_IMAGE_MODEL="${PATCHAPI_EGAKI_IMAGE_MODEL:-gemini-3.1-flash-image-preview}"

log "step 4/4 — live ${EGAKI_IMAGE_MODEL} image call (opt-in)"
LAST_COMMAND="scripts/verify_demo_egaki.sh (live image step)"

LIVE_CHECK="${REPO_ROOT}/demo/egaki/live_image_check.sh"

if [[ "${PATCHAPI_LIVE_IMAGE:-0}" != "1" ]]; then
  skip "live image step not requested (set PATCHAPI_LIVE_IMAGE=1 to run it)"
elif [[ ! -f "${LIVE_CHECK}" ]]; then
  skip "demo/egaki/live_image_check.sh missing"
else
  bash "${LIVE_CHECK}" "${ARTIFACTS}/verification.png" "${EGAKI_IMAGE_MODEL}"
  case "$?" in
    0) pass "live image written to demo/egaki/artifacts/verification.png" ;;
    2) skip "live image step reported missing credentials (see message above)" ;;
    *) fail "live image call failed" ;;
  esac
fi
