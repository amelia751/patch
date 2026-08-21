#!/usr/bin/env bash
# Topics, push subscriptions, and IAM so import/push events reach the indexer.
#
# Idempotent. The worker is Cloud Run + Pub/Sub push, not a Job: messages for
# two repositories queue independently; the same (repo, branch) is serialized
# inside the worker.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
PROJECT_NUMBER="${GCP_PROJECT_NUMBER:-913371146929}"
REGION="${GCP_REGION:-us-central1}"
PREFIX="${PATCHAPI_PUBSUB_TOPIC_PREFIX:-patchapi-dev}"
INDEXER_SERVICE="${PATCHAPI_INDEXER_SERVICE:-patchapi-indexer}"
INDEXER_SA_ID="${PATCHAPI_INDEXER_SA:-patchapi-indexer}"
PUSH_SA_ID="${PATCHAPI_PUBSUB_PUSH_SA:-patchapi-pubsub-push}"
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

INDEXER_SA="$(sa_email "$INDEXER_SA_ID")"
PUSH_SA="$(sa_email "$PUSH_SA_ID")"
API_SA="$(sa_email "$API_SA_ID")"
INDEXER_URL="https://${INDEXER_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"

ensure_api() {
  gcloud services enable "$1" --project="$PROJECT_ID"
}

ensure_sa() {
  local id="$1" display="$2"
  if gcloud iam service-accounts describe "$(sa_email "$id")" --project="$PROJECT_ID" >/dev/null 2>&1; then
    return 0
  fi
  gcloud iam service-accounts create "$id" \
    --project="$PROJECT_ID" \
    --display-name="$display"
}

ensure_topic() {
  local name="$1"
  if gcloud pubsub topics describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    return 0
  fi
  gcloud pubsub topics create "$name" --project="$PROJECT_ID"
}

ensure_push_sub() {
  local topic="$1" sub="$2"
  if gcloud pubsub subscriptions describe "$sub" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud pubsub subscriptions update "$sub" \
      --project="$PROJECT_ID" \
      --push-endpoint="${INDEXER_URL}/v1/events" \
      --push-auth-service-account="$PUSH_SA" \
      --ack-deadline=600 \
      --min-retry-delay=10s \
      --max-retry-delay=600s
    return 0
  fi
  gcloud pubsub subscriptions create "$sub" \
    --project="$PROJECT_ID" \
    --topic="$topic" \
    --push-endpoint="${INDEXER_URL}/v1/events" \
    --push-auth-service-account="$PUSH_SA" \
    --ack-deadline=600 \
    --min-retry-delay=10s \
    --max-retry-delay=600s
}

ensure_api pubsub.googleapis.com
ensure_api run.googleapis.com
ensure_sa "$INDEXER_SA_ID" "PatchAPI repo indexer"
ensure_sa "$PUSH_SA_ID" "PatchAPI Pub/Sub push to Cloud Run"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${INDEXER_SA}" \
  --role="roles/cloudsql.client" \
  --quiet >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${API_SA}" \
  --role="roles/pubsub.publisher" \
  --quiet >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${INDEXER_SA}" \
  --role="roles/pubsub.publisher" \
  --quiet >/dev/null

gcloud iam service-accounts add-iam-policy-binding "$PUSH_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --quiet >/dev/null

for event in repo-push project-repo-added project-repo-removed index-updated; do
  ensure_topic "${PREFIX}-${event}"
  gcloud pubsub topics add-iam-policy-binding "${PREFIX}-${event}" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:${API_SA}" \
    --role="roles/pubsub.publisher" \
    --quiet >/dev/null
  gcloud pubsub topics add-iam-policy-binding "${PREFIX}-${event}" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:${INDEXER_SA}" \
    --role="roles/pubsub.publisher" \
    --quiet >/dev/null
done

for event in repo-push project-repo-added project-repo-removed; do
  ensure_push_sub "${PREFIX}-${event}" "${PREFIX}-${event}-sub"
done

if gcloud run services describe "$INDEXER_SERVICE" --project="$PROJECT_ID" --region="$REGION" >/dev/null 2>&1; then
  gcloud run services add-iam-policy-binding "$INDEXER_SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --member="serviceAccount:${PUSH_SA}" \
    --role="roles/run.invoker" \
    --quiet >/dev/null
fi

printf 'indexer push endpoint: %s/v1/events\n' "$INDEXER_URL"
printf 'topics: %s-{repo-push,project-repo-added,project-repo-removed}\n' "$PREFIX"
