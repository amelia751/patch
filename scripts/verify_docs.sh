#!/usr/bin/env bash
# The public doc is README.md plus the architecture diagram.
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

failures=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

[ -s README.md ] || fail "README.md is missing or empty"
[ -f docs/architecture.png ] || fail "docs/architecture.png is missing"

if [ "$failures" -ne 0 ]; then
  printf 'FAIL: verify_docs.sh — %d problem(s)\n' "$failures" >&2
  exit 1
fi

printf 'PASS: verify_docs.sh\n'
