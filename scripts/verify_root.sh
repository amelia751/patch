#!/usr/bin/env bash
# Dynamic verifier for the root uv workspace (setup.md T-root-workspace).
# Executes the toolchain rather than inspecting filenames: sync, interpreter
# pin, lint, tests. Exits non-zero on any failure and records the outcome in the
# shared setup ledger.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_root.sh"
STATUS="FAIL"

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-root-workspace","status":"%s","command":"%s","at":"%s"}\n' \
    "$STATUS" "$COMMAND" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LEDGER"
}
trap record EXIT

step() { printf '\n== %s\n' "$1"; }

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv is not installed (see setup.md §3)"
  exit 1
fi

step "uv sync"
uv sync

step "interpreter pin"
uv run python -c 'import sys; assert sys.version_info[:2] == (3, 12), f"expected Python 3.12, got {sys.version.split()[0]}"; print(sys.version.split()[0])'

step "ruff check"
uv run ruff check .

step "ruff format --check"
uv run ruff format --check .

step "pytest"
# Root workspace only owns the placeholder suite under tests/unit/. Package and
# service tests have their own verify_*.sh scripts that sync the right extras.
uv run pytest -q tests/unit

STATUS="PASS"
echo
echo "PASS: root workspace verified"
