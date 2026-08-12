#!/usr/bin/env bash
# Dynamic verifier for the skill packages under skills/.
#
# It executes the skill's own checks against real inputs and asserts the exit
# code contract published in skills/google_imagen_migration/skill.json — a
# golden fixture, a drifted fixture, and a tampered provider note that must fail
# closed. Grepping for filenames would not prove the fail-closed path runs.
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SKILL="skills/google_imagen_migration"
CHECKS="$SKILL/checks/run_checks.py"
TESTDATA="$SKILL/checks/testdata"
LEDGER="demo/setup-ledger.ndjson"

failures=0
skips=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

ok() {
  printf 'ok   %s\n' "$*"
}

skip() {
  printf 'SKIP: %s\n' "$*"
  skips=$((skips + 1))
}

# The skill must run on a bare interpreter — that is the point of its
# dependency-free design — but prefer the workspace interpreter when present so
# the tests below run with pytest available.
if command -v uv >/dev/null 2>&1; then
  PY=(uv run python)
elif command -v python3 >/dev/null 2>&1; then
  PY=(python3)
else
  printf 'FAIL: no python3 or uv on PATH\n' >&2
  exit 1
fi

# expect_exit <expected> <label> -- <run_checks args...>
expect_exit() {
  local expected="$1" label="$2"
  shift 3 # drop expected, label, and the literal --
  local actual=0
  "${PY[@]}" "$CHECKS" "$@" >/tmp/verify_skills.out 2>&1 || actual=$?
  if [ "$actual" -eq "$expected" ]; then
    ok "$label (exit $actual)"
  else
    fail "$label expected exit $expected, got $actual"
    sed 's/^/       /' /tmp/verify_skills.out >&2
  fi
}

# --- the exit-code contract -------------------------------------------------

expect_exit 0 "golden fixture is accepted" -- --json
expect_exit 2 "tampered provider note fails closed" -- --scan "$TESTDATA/adversarial-merge-request.md"
expect_exit 1 "drifted fixture is rejected" -- --fixture "$TESTDATA/drifted-fixture.json"
expect_exit 1 "uncaptured provider snapshot fails under --require-snapshot" -- --require-snapshot
expect_exit 1 "missing fixture is an error, never a pass" -- --fixture "$TESTDATA/absent.json"

# The shared adversarial corpus is owned by the demo tree; use it when it is
# there rather than duplicating the fixture here.
INJECTION="demo/adversarial/prompt-injection-provider-note.md"
if [ -f "$INJECTION" ]; then
  expect_exit 2 "demo prompt-injection note fails closed" -- --scan "$INJECTION"
else
  skip "$INJECTION not present — shared adversarial corpus not checked"
fi

# --- the golden verdict is the honest one -----------------------------------

verdict="$("${PY[@]}" "$CHECKS" --json | "${PY[@]}" -c \
  'import json,sys; print(json.load(sys.stdin)["verdict"])')"
case "$verdict" in
  SKILL_APPLICABLE|HUMAN_REQUIRED) ok "golden verdict is $verdict" ;;
  *) fail "golden verdict is $verdict, expected SKILL_APPLICABLE or HUMAN_REQUIRED" ;;
esac

# --- unit tests and lint ----------------------------------------------------

if command -v uv >/dev/null 2>&1; then
  if uv run pytest "$SKILL" -q >/tmp/verify_skills_pytest.out 2>&1; then
    ok "uv run pytest $SKILL -q"
  else
    fail "uv run pytest $SKILL -q"
    tail -30 /tmp/verify_skills_pytest.out >&2
  fi

  if uv run ruff check skills >/tmp/verify_skills_ruff.out 2>&1; then
    ok "uv run ruff check skills"
  else
    fail "uv run ruff check skills"
    tail -30 /tmp/verify_skills_ruff.out >&2
  fi
else
  skip "uv not on PATH — pytest and ruff not run"
fi

# ---------------------------------------------------------------------------

at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [ "$failures" -ne 0 ]; then
  status=FAIL
else
  status=PASS
fi
printf '{"task":"T-skills","status":"%s","command":"./scripts/verify_skills.sh","at":"%s","notes":"%d skip(s)"}\n' \
  "$status" "$at" "$skips" >>"$LEDGER"

if [ "$failures" -ne 0 ]; then
  printf 'FAIL: verify_skills.sh — %d problem(s)\n' "$failures" >&2
  exit 1
fi

printf 'PASS: verify_skills.sh (%d skip(s))\n' "$skips"
