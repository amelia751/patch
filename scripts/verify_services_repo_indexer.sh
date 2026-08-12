#!/usr/bin/env bash
# Dynamic verifier for services/repo_indexer (setup.md T-services-repo_indexer).
#
# Lints and unit-tests the tree, then runs the real CLI against the fixture
# checkout under tests/fixtures/repo_with_imagen/ and asserts the inventory it
# writes: the retired Imagen 4 identifiers are found at the expected paths with
# the expected usage kinds, the vendored copy is absent, a tree with no watched
# identifier yields an empty inventory, and two runs of the same tree produce
# byte-identical output. Exits non-zero on any failure and records the outcome
# in the shared setup ledger.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_services_repo_indexer.sh"
STATUS="FAIL"
WORK_DIR=""

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-services-repo_indexer","status":"%s","command":"%s","at":"%s"}\n' \
    "$STATUS" "$COMMAND" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LEDGER"
}

teardown() {
  [[ -n "$WORK_DIR" ]] && rm -rf "$WORK_DIR"
  record
}
trap teardown EXIT

step() { printf '\n== %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

if ! command -v uv >/dev/null 2>&1; then
  fail "uv is not installed (see setup.md §3)"
fi

FIXTURE="tests/fixtures/repo_with_imagen"
[[ -d "$FIXTURE" ]] || fail "fixture checkout is missing: $FIXTURE"

# The fixture tree is not a git checkout, so the inventory records the git null
# SHA rather than claiming a commit that was never read.
NULL_SHA="0000000000000000000000000000000000000000"
FIXTURE_REPO_NAME="patchapi-fixtures/repo-with-imagen"

# The service imports the shared packages from the checkout rather than from an
# installed wheel, so the probe exercises the source this tree owns.
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/services/repo_indexer/src"

# Preferred path: this package installed from the workspace, which also proves
# it is a real workspace member. `--inexact` so verifying this tree does not
# uninstall a sibling tree's package from the shared environment while another
# worker is using it. If the workspace install is unusable, fall back to an
# isolated environment built from this package's own pinned dependencies.
#
# Set PATCHAPI_VERIFY_ISOLATED=1 to exercise the fallback deliberately.
step "environment"
WORKSPACE_RUN=(
  uv run --inexact --package patchapi-repo-indexer
  --with "pytest>=8.3,<9"
  --with "ruff>=0.14,<0.15"
)
if [[ "${PATCHAPI_VERIFY_ISOLATED:-0}" != "1" ]] &&
  "${WORKSPACE_RUN[@]}" python -c "import pydantic, pytest, patchapi_repo_indexer" \
    >/dev/null 2>&1; then
  echo "workspace environment (--package patchapi-repo-indexer)"
  RUN=("${WORKSPACE_RUN[@]}")
  COMMAND="$COMMAND (workspace)"
else
  echo "NOTE: the workspace install of patchapi-repo-indexer is not usable right now."
  echo "isolated environment"
  RUN=(
    uv run --no-project
    --with "pydantic>=2.9,<3"
    --with "pytest>=8.3,<9"
    --with "ruff>=0.14,<0.15"
  )
  COMMAND="$COMMAND (isolated)"
fi

step "ruff check"
"${RUN[@]}" ruff check services/repo_indexer

step "ruff format --check"
"${RUN[@]}" ruff format --check services/repo_indexer

step "pytest services/repo_indexer"
"${RUN[@]}" python -m pytest services/repo_indexer -q

WORK_DIR="$(mktemp -d -t patchapi-repo-indexer-XXXXXX)"

step "index the fixture checkout"
"${RUN[@]}" python -m patchapi_repo_indexer \
  --root "$FIXTURE" \
  --repository "$FIXTURE_REPO_NAME" \
  --sha "$NULL_SHA" \
  --out "$WORK_DIR/fixture.json"

"${RUN[@]}" python - "$WORK_DIR/fixture.json" <<'PY'
import json
import sys

document = json.load(open(sys.argv[1]))

assert document["scope"] == "full_tree", document["scope"]

by_path = {}
for usage in document["usages"]:
    by_path.setdefault(usage["file_path"], []).append(usage)

# 1. The deterministic hit the whole task exists for.
runtime = by_path.get("src/image.ts", [])
assert len(runtime) == 1, f"expected one runtime hit, got {runtime}"
hit = runtime[0]
assert hit["identifier"] == "imagen-4.0-generate-001", hit
assert hit["usage_kind"] == "runtime_source", hit
assert hit["detection_layer"] == "A_DETERMINISTIC", hit
assert hit["confidence"] == 1.0, hit
assert hit["line_start"] == 3, hit
assert "vertex/imagen-4.0-generate-001" in hit["excerpt"], hit

# 2. Every Imagen 4 identifier present in the tree is reported, and none that
#    is absent is invented.
found = sorted({usage["identifier"] for usage in document["usages"]})
assert found == ["imagen-4.0-fast-generate-001", "imagen-4.0-generate-001"], found

# 3. Documentation and configuration are distinguished from runtime source.
assert by_path["README.md"][0]["usage_kind"] == "documentation_example", by_path["README.md"]
kinds = {usage["usage_kind"] for usage in by_path["config/models.json"]}
assert kinds == {"configuration"}, kinds

# 4. The vendored copy of the same string is not the customer's usage.
vendored = [path for path in by_path if path.startswith("vendor/")]
assert not vendored, f"vendored paths leaked into the inventory: {vendored}"

# 5. The file with no identifier was still read.
assert document["files_scanned"] == 4, document["files_scanned"]

print(f"inventory: {len(document['usages'])} usages across {len(by_path)} files")
print("identifiers:", ", ".join(found))
PY

step "index a checkout with no watched identifier"
EMPTY_TREE="$WORK_DIR/empty-tree"
mkdir -p "$EMPTY_TREE/src"
printf 'export const MODEL = "gemini-3.1-flash-image";\n' >"$EMPTY_TREE/src/app.ts"
printf '# nothing to migrate\n' >"$EMPTY_TREE/README.md"

"${RUN[@]}" python -m patchapi_repo_indexer \
  --root "$EMPTY_TREE" \
  --repository "$FIXTURE_REPO_NAME" \
  --sha "$NULL_SHA" \
  --out "$WORK_DIR/empty.json"

"${RUN[@]}" python - "$WORK_DIR/empty.json" <<'PY'
import json
import sys

document = json.load(open(sys.argv[1]))
assert document["usages"] == [], document["usages"]
# The scan happened and found nothing, which is different from not scanning.
assert document["files_scanned"] == 2, document["files_scanned"]
print("empty tree -> empty inventory, 2 files read")
PY

step "an unaffected checkout is a success, not a failure"
EXIT_CODE=0
"${RUN[@]}" python -m patchapi_repo_indexer \
  --root "$EMPTY_TREE" --repository "$FIXTURE_REPO_NAME" --sha "$NULL_SHA" \
  >/dev/null 2>&1 || EXIT_CODE=$?
[[ "$EXIT_CODE" == "0" ]] || fail "empty inventory exited $EXIT_CODE, expected 0"

step "a scan that cannot be performed fails closed"
EXIT_CODE=0
"${RUN[@]}" python -m patchapi_repo_indexer \
  --root "$WORK_DIR/does-not-exist" --repository "$FIXTURE_REPO_NAME" --sha "$NULL_SHA" \
  >/dev/null 2>&1 || EXIT_CODE=$?
[[ "$EXIT_CODE" == "2" ]] || fail "missing root exited $EXIT_CODE, expected 2"

EXIT_CODE=0
"${RUN[@]}" python -m patchapi_repo_indexer \
  --root "$FIXTURE" --repository "$FIXTURE_REPO_NAME" --sha "$NULL_SHA" \
  --provider acme >/dev/null 2>&1 || EXIT_CODE=$?
[[ "$EXIT_CODE" == "2" ]] || fail "unknown provider exited $EXIT_CODE, expected 2"
echo "missing root and unknown provider both exit 2"

step "two indexes of the same tree are byte-identical"
"${RUN[@]}" python -m patchapi_repo_indexer \
  --root "$FIXTURE" --repository "$FIXTURE_REPO_NAME" --sha "$NULL_SHA" \
  --out "$WORK_DIR/again.json"
cmp -s "$WORK_DIR/fixture.json" "$WORK_DIR/again.json" ||
  fail "the same tree produced two different inventories"
echo "deterministic across runs"

step "changed-paths index is narrowed and marked partial"
"${RUN[@]}" python -m patchapi_repo_indexer \
  --root "$FIXTURE" --repository "$FIXTURE_REPO_NAME" --sha "$NULL_SHA" \
  --changed-path src/image.ts \
  --out "$WORK_DIR/changed.json"

"${RUN[@]}" python - "$WORK_DIR/changed.json" <<'PY'
import json
import sys

document = json.load(open(sys.argv[1]))
assert document["scope"] == "changed_paths", document["scope"]
assert document["files_scanned"] == 1, document["files_scanned"]
paths = {usage["file_path"] for usage in document["usages"]}
assert paths == {"src/image.ts"}, paths
print("changed-paths scope:", ", ".join(sorted(paths)))
PY

STATUS="PASS"
echo
echo "PASS: services/repo_indexer verified"
