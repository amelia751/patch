#!/usr/bin/env bash
# Dynamic verifier for packages/providers (setup.md T-packages-providers-google).
#
# Two halves, both required to run:
#   offline — the pinned Google deprecation fixture is normalized into a real
#             ChangeManifest, and every golden document that must be refused is
#             refused. Never skipped.
#   live    — one real Vertex generateContent call to the pinned reasoning model
#             on locations/global. SKIP only when credentials are genuinely
#             absent; the smoke has no path that prints PASS without a response
#             from Google.
#
# Set PATCHAPI_REQUIRE_LIVE=1 to make an honest SKIP a failure (what CI and the
# aggregate verifier should do once credentials are provisioned).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_packages_providers_google.sh"
STATUS="FAIL"
NOTES="did not complete"

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-packages-providers-google","status":"%s","command":"%s","at":"%s","notes":"%s"}\n' \
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
# not a defect in this adapter — fall back to an isolated environment built from
# this package's own pinned dependencies so it stays verifiable either way.
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
    --with "google-auth>=2.38,<3"
    --with "requests>=2.32,<3"
  )
  COMMAND="$COMMAND (isolated)"
fi

step "adapter imports and pins"
"${RUN[@]}" python -c '
import packages.providers.google as g

print("provider:      ", g.PROVIDER_ID)
print("adapter:       ", g.ADAPTER_VERSION)
print("reasoning pin: ", g.DEFAULT_REASONING_MODEL)
print("image pin:     ", g.DEFAULT_IMAGE_MODEL)
print("vertex location:", g.DEFAULT_VERTEX_LOCATION)
assert g.DEFAULT_VERTEX_LOCATION == "global", "Gemini 3.x is served from the global endpoint"
g.require_supported_reasoning_model(g.DEFAULT_REASONING_MODEL)
g.require_supported_image_model(g.DEFAULT_IMAGE_MODEL)
'

step "offline: fixture -> ChangeManifest"
"${RUN[@]}" python -c '
from pathlib import Path

from packages.providers.google.normalize import manifest_from_feed_file

fixture = Path("demo/fixtures/google-imagen4-deprecation.json")
manifest = manifest_from_feed_file(fixture)
print("source:      ", fixture)
print("change_id:   ", manifest.change_id)
print("change_type: ", manifest.change_type)
print("severity:    ", manifest.severity)
print("retires:     ", ", ".join(manifest.affected_identifiers))
print("replacement: ", manifest.recommended_replacement)
print("semantic:    ", manifest.semantic_migration_required)
print("constraints: ", len(manifest.migration_constraints))
print("evidence:    ", "hashed snapshot" if manifest.has_verifiable_evidence else "none (fails closed)")
assert manifest.retires("imagen-4.0-generate-001")
assert manifest.recommended_replacement == "gemini-3.1-flash-image"
assert manifest.semantic_migration_required is True
'

step "pytest packages/providers"
"${RUN[@]}" pytest packages/providers -q

step "ruff check"
"${RUN[@]}" ruff check packages/providers scripts/smoke_gemini_vertex.py

step "ruff format --check"
"${RUN[@]}" ruff format --check packages/providers scripts/smoke_gemini_vertex.py

step "live: Vertex gemini-3.5-flash on locations/global"
set +e
"${RUN[@]}" python scripts/smoke_gemini_vertex.py
LIVE_RC=$?
set -e

case "$LIVE_RC" in
  0)
    NOTES="offline PASS; live Vertex reasoning smoke PASS"
    ;;
  3)
    if [[ "${PATCHAPI_REQUIRE_LIVE:-0}" == "1" ]]; then
      echo "FAIL: live smoke skipped but PATCHAPI_REQUIRE_LIVE=1"
      NOTES="live smoke SKIP while required"
      exit 1
    fi
    NOTES="offline PASS; live smoke SKIP (credentials absent)"
    STATUS="SKIP"
    echo
    echo "SKIP: offline verification passed; the live Vertex call was skipped."
    echo "      Provide .secrets/gcp-service-account.json and GCP_PROJECT to run it."
    exit 0
    ;;
  *)
    NOTES="live Vertex smoke FAIL (exit $LIVE_RC)"
    exit "$LIVE_RC"
    ;;
esac

STATUS="PASS"
echo
echo "PASS: packages/providers verified (offline normalization + live Vertex reasoning call)"
