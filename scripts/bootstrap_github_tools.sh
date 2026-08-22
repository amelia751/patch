#!/usr/bin/env bash
# Identity for the narrow GitHub capability adapter.
#
# The service itself is deployed by `.github/workflows/deploy-cloud-run.yml`.
# What has to exist first is the identity it runs as, which is the only one in
# the fleet allowed to read the GitHub App private key.
#
# Thinner than every other lane on purpose. This service holds the credential
# that can write to a customer's repository, so it gets no database, no model,
# no Pub/Sub, and no project-level role beyond writing its own logs. Callers
# reach it over Cloud Run IAM; it is never public.
#
# Idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${PATCHAPI_GHTOOLS_SERVICE:-patchapi-github-tools}"
GHTOOLS_SA_ID="${PATCHAPI_GHTOOLS_SA:-patchapi-github-tools}"
AGENTS_SA_ID="${PATCHAPI_AGENTS_SA:-patchapi-agents}"
API_SA_ID="${PATCHAPI_API_SA:-patchapi-api}"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"

if [[ -f "$KEY_FILE" ]]; then
  export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$KEY_FILE"
fi
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

sa_email() {
  printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT_ID"
}

GHTOOLS_SA="$(sa_email "$GHTOOLS_SA_ID")"

ensure_sa() {
  local id="$1" display="$2"
  if gcloud iam service-accounts describe "$(sa_email "$id")" --project="$PROJECT_ID" >/dev/null 2>&1; then
    return 0
  fi
  gcloud iam service-accounts create "$id" --project="$PROJECT_ID" --display-name="$display"
  # IAM is eventually consistent; a binding issued immediately after creation
  # fails with "service account does not exist".
  sleep 10
}

gcloud services enable run.googleapis.com secretmanager.googleapis.com --project="$PROJECT_ID"

ensure_sa "$GHTOOLS_SA_ID" "PatchAPI GitHub capability adapter"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${GHTOOLS_SA}" --role=roles/logging.logWriter \
  --condition=None --quiet >/dev/null

# The App credentials, and nothing else. Read access is granted per secret
# rather than at the project level so this identity cannot read the database
# DSN, the session secret, or the model key.
for secret in patchapi-github-app-id patchapi-github-app-installation-id patchapi-github-app-private-key; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --project="$PROJECT_ID" --member="serviceAccount:${GHTOOLS_SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
done

# Who may call it. The agent lane opens the pull request; the control plane
# reads PR state for the console. Neither receives the private key.
if gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION" >/dev/null 2>&1; then
  for caller in "$AGENTS_SA_ID" "$API_SA_ID"; do
    gcloud run services add-iam-policy-binding "$SERVICE" \
      --project="$PROJECT_ID" --region="$REGION" \
      --member="serviceAccount:$(sa_email "$caller")" \
      --role=roles/run.invoker --quiet >/dev/null
  done
  printf 'invokers: %s, %s\n' "$(sa_email "$AGENTS_SA_ID")" "$(sa_email "$API_SA_ID")"
else
  printf 'service %s not deployed yet; rerun after the workflow creates it to grant invokers\n' "$SERVICE"
fi

printf 'service account %s\n' "$GHTOOLS_SA"
