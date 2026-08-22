#!/usr/bin/env bash
# Identity and plumbing for the Change Intelligence lane.
#
# The service itself is deployed by `.github/workflows/deploy-cloud-run.yml`.
# What has to exist first is the identity it runs as and the subscription that
# feeds it, neither of which belongs in a per-push workflow.
#
# The grants are deliberately thinner than the indexer's. This lane calls a
# model and updates four columns on a change event; it never clones a
# repository, never touches GitHub, and holds no publish rights at all, so it
# cannot re-announce a change and loop itself.
#
# Idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${PATCHAPI_AGENTS_SERVICE:-patchapi-agents}"
AGENTS_SA_ID="${PATCHAPI_AGENTS_SA:-patchapi-agents}"
PUSH_SA_ID="${PATCHAPI_PUSH_SA:-patchapi-pubsub-push}"
PREFIX="${PATCHAPI_PUBSUB_TOPIC_PREFIX:-patchapi-dev}"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"

if [[ -f "$KEY_FILE" ]]; then
  export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$KEY_FILE"
fi
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

sa_email() {
  printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT_ID"
}

AGENTS_SA="$(sa_email "$AGENTS_SA_ID")"
PUSH_SA="$(sa_email "$PUSH_SA_ID")"

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

gcloud services enable run.googleapis.com aiplatform.googleapis.com --project="$PROJECT_ID"

ensure_sa "$AGENTS_SA_ID" "PatchAPI Change Intelligence lane"

# aiplatform.user, not viewer: this identity calls generateContent. Cloud SQL to
# read the change event and write the rationale back onto it.
for role in roles/aiplatform.user roles/cloudsql.client roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${AGENTS_SA}" --role="$role" --condition=None --quiet >/dev/null
done

for secret in patchapi-database-url patchapi-gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --project="$PROJECT_ID" --member="serviceAccount:${AGENTS_SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
done

printf 'service account %s\n' "$AGENTS_SA"
printf 'subscription %s-change-normalized-sub is pointed at the service by the deploy workflow\n' "$PREFIX"
printf 'push identity %s\n' "$PUSH_SA"
