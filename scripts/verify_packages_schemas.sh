#!/usr/bin/env bash
# Dynamic verifier for packages/schemas (setup.md T-packages-schemas).
# Loads the golden contract documents through the real parsers, proves each one
# round-trips as JSON, and proves the manifests that must be refused are
# refused. Exits non-zero on any failure and records the outcome in the shared
# setup ledger.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_packages_schemas.sh"
STATUS="FAIL"

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-packages-schemas","status":"%s","command":"%s","at":"%s"}\n' \
    "$STATUS" "$COMMAND" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LEDGER"
}
trap record EXIT

step() { printf '\n== %s\n' "$1"; }

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv is not installed (see setup.md §3)"
  exit 1
fi

# Preferred path: the shared workspace environment. A workspace member in
# another tree that is mid-flight makes `uv sync` fail for every tree, which is
# not a defect in these schemas — fall back to an isolated environment built
# from this package's own pinned dependencies so the contracts stay verifiable.
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
    --with "pydantic>=2.9,<3"
    --with "pytest>=8.3,<9"
    --with "pytest-asyncio>=1.0,<2"
    --with "ruff>=0.14,<0.15"
  )
  COMMAND="$COMMAND (isolated)"
fi

step "contracts import"
"${RUN[@]}" python -c '
import packages.schemas as s

required = [
    "ChangeManifest",
    "ImpactReport",
    "PolicyDecision",
    "PatchPlan",
    "VerificationReport",
    "RunState",
]
missing = [name for name in required if not hasattr(s, name)]
assert not missing, f"missing contracts: {missing}"
print("contracts:", ", ".join(required))
print("pinned versions:", dict(s.CONTRACT_VERSIONS))
'

step "pytest packages/schemas"
"${RUN[@]}" pytest packages/schemas -q

step "ruff check"
"${RUN[@]}" ruff check packages/schemas

step "ruff format --check"
"${RUN[@]}" ruff format --check packages/schemas

STATUS="PASS"
echo
echo "PASS: packages/schemas verified"
