#!/usr/bin/env bash
# Live replacement-model proof: drive the *pinned Egaki CLI* (not a re-implementation)
# to generate an image with the Gemini replacement model, then assert real bytes.
#
# Using the built CLI is the point: the roadmap's verification step must exercise
# the same SDK stack and code path the migrated repository will ship.
#
# Credential note (measured against the pinned SHA, see expected-findings.yaml):
# Egaki resolves Google credentials only from GOOGLE_GENERATIVE_AI_API_KEY
# (AI Studio) or GOOGLE_VERTEX_API_KEY (Vertex express key). It does NOT accept
# Application Default Credentials / service-account JSON, so
# GOOGLE_APPLICATION_CREDENTIALS alone cannot satisfy this check.
#
# Usage: demo/egaki/live_image_check.sh <output.png> [model-id]

set -euo pipefail

OUT="${1:?usage: live_image_check.sh <output.png> [model-id]}"
MODEL="${2:-gemini-3.1-flash-image-preview}"
PROMPT="a tiny orange cat wearing a space helmet on a plain background"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
CLI="${HERE}/checkout/cli/dist/cli/main.js"

[[ -f "${CLI}" ]] || { echo "FAIL: ${CLI} not built — run pnpm --dir cli build first" >&2; exit 1; }

# Load a key from the environment, else from the gitignored secrets file.
if [[ -z "${GOOGLE_GENERATIVE_AI_API_KEY:-}" && -f "${REPO_ROOT}/.secrets/gemini_api_key.txt" ]]; then
  GOOGLE_GENERATIVE_AI_API_KEY="$(tr -d '[:space:]' < "${REPO_ROOT}/.secrets/gemini_api_key.txt")"
  export GOOGLE_GENERATIVE_AI_API_KEY
fi

if [[ -z "${GOOGLE_GENERATIVE_AI_API_KEY:-}" && -z "${GOOGLE_VERTEX_API_KEY:-}" ]]; then
  echo "SKIP: no GOOGLE_GENERATIVE_AI_API_KEY or GOOGLE_VERTEX_API_KEY (ADC is not accepted by the pinned CLI)" >&2
  exit 2
fi

mkdir -p "$(dirname "${OUT}")"
rm -f "${OUT}"

echo "invoking: egaki image <prompt> -m ${MODEL} -o ${OUT}"
LOG="$(dirname "${OUT}")/live_image_check.log"
set +e
node "${CLI}" image "${PROMPT}" -m "${MODEL}" -o "${OUT}" 2>&1 | tee "${LOG}"
CLI_STATUS="${PIPESTATUS[0]}"
set -e

if [[ "${CLI_STATUS}" -ne 0 ]]; then
  # An exhausted or unauthorized credential is a missing precondition, not a
  # defect in the migration — report it as SKIP so it can never be mistaken for
  # a verified live call. Every other failure stays a hard FAIL.
  if grep -qE 'RESOURCE_EXHAUSTED|prepayment credits|quota|PERMISSION_DENIED|UNAUTHENTICATED|API key not valid' "${LOG}"; then
    echo "SKIP: credential unusable for ${MODEL} — see ${LOG}" >&2
    exit 2
  fi
  echo "FAIL: egaki exited ${CLI_STATUS} for ${MODEL} — see ${LOG}" >&2
  exit 1
fi

[[ -s "${OUT}" ]] || { echo "FAIL: ${OUT} missing or empty" >&2; exit 1; }

# Assert real image bytes, not an error page written to disk.
python3 - "${OUT}" <<'PY'
import sys
path = sys.argv[1]
head = open(path, "rb").read(12)
size = __import__("os").path.getsize(path)
if head.startswith(b"\x89PNG\r\n\x1a\n"):
    kind = "PNG"
elif head.startswith(b"\xff\xd8\xff"):
    kind = "JPEG"
elif head[4:12] in (b"ftypavif", b"ftypheic"):
    kind = "AVIF/HEIC"
else:
    sys.exit(f"FAIL: {path} is not a recognized image (magic={head[:8]!r})")
print(f"PASS: {path} is a valid {kind}, {size} bytes")
PY
