#!/usr/bin/env bash
# Deploy Storygen to Cloud Run in artful-journey. Service name is the URL.
# Uses the development key. Runtime identity is jetrun-viewer, which already
# has secretAccessor — development cannot setIamPolicy on Secret Manager.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PROJECT_ID="${GCP_PROJECT:-artful-journey-486915-a8}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${STORYGEN_SERVICE:-storygen}"
DEV_KEY="${STORYGEN_DEV_KEY:-$HERE/../artful-journey-486915-a8-fc72d9d68c0b.json}"
GEMINI_KEY_FILE="${GEMINI_API_KEY_FILE:-$ROOT/.secrets/gemini_api_key.txt}"
SECRET_NAME="${STORYGEN_SECRET:-storygen-gemini-api-key}"
RUNTIME_SA="${STORYGEN_RUNTIME_SA:-jetrun-viewer@${PROJECT_ID}.iam.gserviceaccount.com}"

if [[ ! -f "$DEV_KEY" ]]; then
  printf 'missing development key: %s\n' "$DEV_KEY" >&2
  exit 1
fi
if [[ ! -f "$GEMINI_KEY_FILE" ]]; then
  printf 'missing Gemini key file: %s\n' "$GEMINI_KEY_FILE" >&2
  exit 1
fi

export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$DEV_KEY"
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

if ! gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET_NAME" --project="$PROJECT_ID" --replication-policy=automatic
fi
gcloud secrets versions add "$SECRET_NAME" --project="$PROJECT_ID" --data-file="$GEMINI_KEY_FILE"

gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source="$HERE" \
  --allow-unauthenticated \
  --service-account="$RUNTIME_SA" \
  --set-secrets="GEMINI_API_KEY=${SECRET_NAME}:latest" \
  --port=8080

STABLE="https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
printf '\nSTABLE_URL=%s\n' "$STABLE"
