#!/usr/bin/env bash
# Cross-cutting live model proofs for setup.md T-gemini-live.
#
# Two checks, both required by the hackathon rules:
#   A. reasoning — Gemini 3.5 Flash answers a real Vertex generateContent call
#                  on locations/global (scripts/smoke_gemini_vertex.py).
#   B. image     — gemini-3.1-flash-image returns inline bytes that carry an
#                  image file signature, written to disk under .secrets/
#                  (scripts/smoke_gemini_image.py).
#
# This verifier defaults to require-live: an honest SKIP for absent credentials
# is a FAIL here, because setup.md §5 says a skipped Gemini proof means setup is
# not complete. Set PATCHAPI_REQUIRE_LIVE=0 to accept a documented SKIP instead.
#
# The artifact check is deliberately not the smoke script's own word: this
# script re-measures the file on disk and, where `file(1)` exists, asks it
# independently whether the bytes are an image.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_gemini_live.sh"
STATUS="FAIL"
NOTES="did not complete"

# Gitignored: generated media is evidence for a run, not source.
ART_DIR=".secrets/smoke-artifacts"
ART_GLOB="gemini-image-smoke"
MIN_IMAGE_BYTES=1024

record() {
  mkdir -p "$(dirname "$LEDGER")"
  printf '{"task":"T-gemini-live","status":"%s","command":"%s","at":"%s","notes":"%s"}\n' \
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
# not a defect in these smokes — fall back to an isolated environment built from
# the pins the provider adapter needs so the live proof stays runnable.
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
    --with "google-auth>=2.38,<3"
    --with "requests>=2.32,<3"
    --with "ruff>=0.14,<0.15"
  )
  COMMAND="$COMMAND (isolated)"
fi

step "lint the smoke scripts"
"${RUN[@]}" ruff check scripts/smoke_gemini_image.py scripts/smoke_gemini_vertex.py
"${RUN[@]}" ruff format --check scripts/smoke_gemini_image.py scripts/smoke_gemini_vertex.py

# Shared by both checks: 0 PASS, 3 SKIP (credentials absent), anything else FAIL.
handle_rc() {
  local label="$1" rc="$2"
  case "$rc" in
    0) return 0 ;;
    3)
      if [[ "${PATCHAPI_REQUIRE_LIVE:-1}" == "1" ]]; then
        echo "FAIL: $label smoke reported SKIP, but this verifier requires a live call."
        echo "      Provide .secrets/gcp-service-account.json and GCP_PROJECT (see .env.example),"
        echo "      or re-run with PATCHAPI_REQUIRE_LIVE=0 to accept a documented SKIP."
        STATUS="FAIL"
        NOTES="$label smoke SKIP while live is required"
        exit 1
      fi
      STATUS="SKIP"
      NOTES="$label smoke SKIP (credentials absent, PATCHAPI_REQUIRE_LIVE=0)"
      echo
      echo "SKIP: $label smoke could not run; credentials are absent and live is not required."
      exit 0
      ;;
    *)
      NOTES="$label smoke FAIL (exit $rc)"
      exit "$rc"
      ;;
  esac
}

step "A. live reasoning: gemini-3.5-flash on locations/global"
set +e
"${RUN[@]}" python scripts/smoke_gemini_vertex.py
TEXT_RC=$?
set -e
handle_rc "reasoning" "$TEXT_RC"

step "B. live image: gemini-3.1-flash-image -> $ART_DIR/"
mkdir -p "$ART_DIR"
rm -f "$ART_DIR/$ART_GLOB".*
set +e
"${RUN[@]}" python scripts/smoke_gemini_image.py
IMAGE_RC=$?
set -e
handle_rc "image" "$IMAGE_RC"

step "B. artifact on disk"
ARTIFACT="$(ls -1 "$ART_DIR/$ART_GLOB".* 2>/dev/null | head -n 1 || true)"
if [[ -z "$ARTIFACT" ]]; then
  echo "FAIL: the image smoke exited 0 but wrote no file under $ART_DIR/"
  NOTES="image smoke wrote no artifact"
  exit 1
fi

BYTES="$(wc -c <"$ARTIFACT" | tr -d ' ')"
if [[ "$BYTES" -lt "$MIN_IMAGE_BYTES" ]]; then
  echo "FAIL: $ARTIFACT is $BYTES bytes; too small to be a render"
  NOTES="image artifact only $BYTES bytes"
  exit 1
fi
echo "artifact: $ARTIFACT ($BYTES bytes)"

if command -v file >/dev/null 2>&1; then
  DESCRIPTION="$(file -b "$ARTIFACT")"
  echo "file(1):  $DESCRIPTION"
  case "$DESCRIPTION" in
    *image*|*bitmap*) ;;
    *)
      echo "FAIL: file(1) does not consider $ARTIFACT an image"
      NOTES="file(1) rejected the artifact: $DESCRIPTION"
      exit 1
      ;;
  esac
else
  echo "NOTE: file(1) unavailable; relying on the smoke's own signature check"
fi

STATUS="PASS"
NOTES="live reasoning PASS; live image PASS ($BYTES bytes)"
echo
echo "PASS: Gemini live proofs — reasoning text and a $BYTES-byte image from Vertex"
