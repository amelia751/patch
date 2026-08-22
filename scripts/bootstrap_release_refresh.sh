#!/usr/bin/env bash
# The scheduled probe that keeps the Releases tab honest.
#
# Classification reads `identifier_probes` to tell a model that is actually gone
# from one that merely has a date typed against it. Probing every indexed
# identifier costs several calls to a Google surface, which is far too slow to
# hang off a page load, so nothing writes that table during a request. This
# provisions the batch half: a Cloud Run job on the control-plane image, run
# every six hours by Cloud Scheduler.
#
# A job rather than an endpoint on purpose. The control plane is public because
# the browser calls it; adding a privileged "reclassify everything" route there
# would widen that surface for no gain.
#
# Idempotent. Re-run after any image change to repoint the job at a new tag.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
REGION="${GCP_REGION:-us-central1}"
JOB="${PATCHAPI_REFRESH_JOB:-patchapi-refresh-releases}"
REFRESH_SA_ID="${PATCHAPI_REFRESH_SA:-patchapi-refresh}"
SCHEDULER_SA_ID="${PATCHAPI_SCHEDULER_SA:-patchapi-scheduler}"
API_SA_ID="${PATCHAPI_API_SA:-patchapi-api}"
SCHEDULE="${PATCHAPI_REFRESH_SCHEDULE:-0 */6 * * *}"
PREFIX="${PATCHAPI_PUBSUB_TOPIC_PREFIX:-patchapi-dev}"
SQL_INSTANCE="${PATCHAPI_SQL_INSTANCE:-${PROJECT_ID}:${REGION}:patchapi-console}"
IMAGE_TAG="${PATCHAPI_IMAGE_TAG:-$(git rev-parse HEAD)}"
IMAGE="${PATCHAPI_REFRESH_IMAGE:-${REGION}-docker.pkg.dev/${PROJECT_ID}/patchapi/api:${IMAGE_TAG}}"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"

if [[ -f "$KEY_FILE" ]]; then
  export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$KEY_FILE"
fi
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

sa_email() {
  printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT_ID"
}

REFRESH_SA="$(sa_email "$REFRESH_SA_ID")"
SCHEDULER_SA="$(sa_email "$SCHEDULER_SA_ID")"

ensure_api() {
  gcloud services enable "$1" --project="$PROJECT_ID"
}

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

ensure_api run.googleapis.com
ensure_api cloudscheduler.googleapis.com
ensure_api aiplatform.googleapis.com

ensure_sa "$REFRESH_SA_ID" "PatchAPI scheduled release refresh"
ensure_sa "$SCHEDULER_SA_ID" "PatchAPI Cloud Scheduler invoker"

# The job reads Vertex listings, reaches Cloud SQL, and writes logs. It has no
# write access to any Google surface and no role on the control plane.
for role in roles/aiplatform.viewer roles/cloudsql.client roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${REFRESH_SA}" --role="$role" --condition=None --quiet >/dev/null
done

for secret in patchapi-database-url patchapi-gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --project="$PROJECT_ID" --member="serviceAccount:${REFRESH_SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
done

# The poller announces transitions; it does not act on them. Publish rights are
# scoped to the two topics it emits on, and it holds no subscriber role at all.
for topic in "${PREFIX}-provider-change-detected" "${PREFIX}-change-normalized"; do
  gcloud pubsub topics add-iam-policy-binding "$topic" \
    --project="$PROJECT_ID" --member="serviceAccount:${REFRESH_SA}" \
    --role=roles/pubsub.publisher --quiet >/dev/null
done

# GOOGLE_API_KEY reaches the Gemini surface. Vertex is reached with the job's
# own identity through application default credentials, so no service account
# key is mounted.
JOB_ARGS=(
  --project="$PROJECT_ID"
  --region="$REGION"
  --image="$IMAGE"
  --service-account="$REFRESH_SA"
  --set-cloudsql-instances="$SQL_INSTANCE"
  # Cloud Run does not set these. Without a project the publisher resolves no
  # topic and the poll degrades to a silent batch run.
  --set-env-vars="GCP_PROJECT=${PROJECT_ID},PATCHAPI_PUBSUB_TOPIC_PREFIX=${PREFIX}"
  --set-secrets="DATABASE_URL=patchapi-database-url:latest,GOOGLE_API_KEY=patchapi-gemini-api-key:latest"
  --command=patchapi-refresh-releases
  --max-retries=1
  --task-timeout=900
  --memory=1Gi
  --cpu=1
)
if gcloud run jobs describe "$JOB" --project="$PROJECT_ID" --region="$REGION" >/dev/null 2>&1; then
  gcloud run jobs update "$JOB" "${JOB_ARGS[@]}" --quiet
else
  gcloud run jobs create "$JOB" "${JOB_ARGS[@]}" --quiet
fi

# Scoped to this one job rather than project-wide run.invoker: neither caller
# has a reason to be able to execute anything else. The control plane is here
# because the console's "Check now" button starts this same job rather than
# reimplementing the poll inside a request.
for caller in "$SCHEDULER_SA" "$(sa_email "$API_SA_ID")"; do
  gcloud run jobs add-iam-policy-binding "$JOB" \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:${caller}" --role=roles/run.invoker --quiet >/dev/null
done

SCHEDULER_ARGS=(
  --project="$PROJECT_ID"
  --location="$REGION"
  --schedule="$SCHEDULE"
  --time-zone=Etc/UTC
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB}:run"
  --http-method=POST
  --oauth-service-account-email="$SCHEDULER_SA"
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
  --attempt-deadline=180s
  --description="Probe indexed identifiers and refresh the Releases tab"
)
if gcloud scheduler jobs describe "$JOB" --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$JOB" "${SCHEDULER_ARGS[@]}" --quiet >/dev/null
else
  gcloud scheduler jobs create http "$JOB" "${SCHEDULER_ARGS[@]}" --quiet >/dev/null
fi

printf 'job %s -> %s\nschedule %s\n' "$JOB" "$IMAGE" "$SCHEDULE"
printf 'run now: gcloud run jobs execute %s --region=%s --wait\n' "$JOB" "$REGION"
