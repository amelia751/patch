#!/usr/bin/env bash
# The Cloud Run worker pool that performs remediations.
#
# Replaces one job execution per run with instances that are already running.
# The job's docstring argued for a job over a request handler because a
# remediation takes minutes, and it was right about requests and wrong about the
# conclusion. Measured on the Cloud Run *task* API — the execution API reports a
# misleading `+13s` — a task that did nothing but read one row waited 136.0s for
# an instance and then lived 5.6s. There is no `min-instances` on a job, and an
# operator hold ends the execution, so Continue paid the 136s again.
#
# A worker pool is the primitive for this: pull-based, no HTTP surface, a
# minimum instance count, and it stays alive across an operator hold. Same image,
# same identity, same narrow capabilities as the job — only the command differs.
#
# The job stays deployed. `bootstrap_remediation_job.sh` is still how one run is
# replayed by hand, and the API prefers this pool over it whenever
# PATCHAPI_REMEDIATION_WORKER_POOL is set.
#
# Idempotent. Re-run after any image change to repoint the pool at a new tag.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
REGION="${GCP_REGION:-us-central1}"
POOL="${PATCHAPI_REMEDIATION_WORKER_POOL:-patchapi-remediate-worker}"
# The same identity the job runs as: Cloud SQL, Vertex, one GKE namespace, and
# invoker on github-tools. No Pub/Sub role, no Secret Manager write, no GitHub
# credential. Sharing it is deliberate — two identities for one job would be two
# things to keep narrow.
RUN_SA_ID="${PATCHAPI_REMEDIATION_SA:-patchapi-remediate}"
SQL_INSTANCE="${PATCHAPI_SQL_INSTANCE:-${PROJECT_ID}:${REGION}:patchapi-console}"
IMAGE_TAG="${PATCHAPI_IMAGE_TAG:-$(git rev-parse HEAD)}"
IMAGE="${PATCHAPI_AGENTS_IMAGE:-${REGION}-docker.pkg.dev/${PROJECT_ID}/patchapi/agents:${IMAGE_TAG}}"
GKE_CLUSTER="${PATCHAPI_GKE_CLUSTER:-patchapi-dev-agentsandbox}"
GKE_LOCATION="${PATCHAPI_GKE_LOCATION:-us-central1-a}"
SANDBOX_NAMESPACE="${PATCHAPI_SANDBOX_NAMESPACE:-patchapi-sandbox-dev}"
GITHUB_TOOLS_URL="${PATCHAPI_GITHUB_TOOLS_URL:-https://patchapi-github-tools-uhkx74fgmq-uc.a.run.app}"
GITHUB_TOOLS_SERVICE="${PATCHAPI_GITHUB_TOOLS_SERVICE:-patchapi-github-tools}"
EVIDENCE_BASE_URL="${PATCHAPI_EVIDENCE_BASE_URL:-https://patchapi-api-913371146929.us-central1.run.app}"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"

# How many remediations this deployment can perform at once, because a worker
# performs one at a time and worker pools do not autoscale. A remediation holds a
# sandbox, drives one run row, and spends most of its life waiting on a model or
# on `kubectl`, so instances are the unit of concurrency here rather than threads
# inside one.
#
# Two, not one. One instance made every second run wait for the first to finish,
# with nothing in the console distinguishing that from a worker that had died —
# and an operator who starts a remediation on one deprecation and then another is
# the ordinary case, not a stress test. Kept small deliberately: each concurrent
# run wants a warm sandbox from the pool in `sandbox/gke/warm-pool.yaml`, so the
# two numbers are raised together or the extra instance waits on a cold sandbox.
INSTANCES="${PATCHAPI_REMEDIATION_WORKER_INSTANCES:-2}"

if [[ -f "$KEY_FILE" ]]; then
  export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$KEY_FILE"
fi
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

sa_email() {
  printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT_ID"
}

RUN_SA="$(sa_email "$RUN_SA_ID")"

if ! gcloud iam service-accounts describe "$RUN_SA" --project="$PROJECT_ID" >/dev/null 2>&1; then
  printf 'error: %s does not exist; run scripts/bootstrap_remediation_job.sh first\n' "$RUN_SA" >&2
  exit 1
fi

gcloud services enable run.googleapis.com --project="$PROJECT_ID"

# The pool reads the same two secrets as the job. Granting again is a no-op when
# the job bootstrap already did it, and is what makes this script runnable alone.
for secret in patchapi-database-url patchapi-gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --project="$PROJECT_ID" --member="serviceAccount:${RUN_SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
done

if [[ -n "$GITHUB_TOOLS_URL" ]]; then
  gcloud run services add-iam-policy-binding "$GITHUB_TOOLS_SERVICE" \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:${RUN_SA}" --role=roles/run.invoker --quiet >/dev/null
fi

ENV_VARS="GCP_PROJECT=${PROJECT_ID}"
# Which runs this pool may claim, and the same value the control plane writes
# onto a row it dispatches. The Cloud SQL instance is shared with every laptop
# running the proxy, so a worker without a lane performs developers' runs and
# their workers perform the deployment's.
ENV_VARS="${ENV_VARS},PATCHAPI_REMEDIATION_WORKER_POOL=${POOL}"
ENV_VARS="${ENV_VARS},GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
ENV_VARS="${ENV_VARS},GCP_VERTEX_LOCATION=global"
ENV_VARS="${ENV_VARS},PATCHAPI_ENV=cloud"
ENV_VARS="${ENV_VARS},PATCHAPI_REPO_ROOT=/app"
ENV_VARS="${ENV_VARS},PATCHAPI_FEED_DIR=/app/demo/fixtures"
ENV_VARS="${ENV_VARS},PATCHAPI_GKE_PROJECT=${PROJECT_ID}"
ENV_VARS="${ENV_VARS},PATCHAPI_GKE_CLUSTER=${GKE_CLUSTER}"
ENV_VARS="${ENV_VARS},PATCHAPI_GKE_LOCATION=${GKE_LOCATION}"
ENV_VARS="${ENV_VARS},PATCHAPI_SANDBOX_NAMESPACE=${SANDBOX_NAMESPACE}"
ENV_VARS="${ENV_VARS},PATCHAPI_EVIDENCE_BASE_URL=${EVIDENCE_BASE_URL}"
if [[ -n "$GITHUB_TOOLS_URL" ]]; then
  ENV_VARS="${ENV_VARS},PATCHAPI_GITHUB_TOOLS_URL=${GITHUB_TOOLS_URL}"
fi

# `--scaling=<n>` is manual scaling. Worker pools do not autoscale on their own,
# and 0 means the workload never starts, so this is the one flag that decides
# whether a run is picked up at all.
gcloud beta run worker-pools deploy "$POOL" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$RUN_SA" \
  --set-cloudsql-instances="$SQL_INSTANCE" \
  --set-env-vars="$ENV_VARS" \
  --set-secrets="DATABASE_URL=patchapi-database-url:latest,GOOGLE_API_KEY=patchapi-gemini-api-key:latest" \
  --command=patchapi-remediation-worker \
  --scaling="$INSTANCES" \
  --memory=4Gi \
  --cpu=2 \
  --quiet

printf 'worker pool %s -> %s (%s instance(s))\n' "$POOL" "$IMAGE" "$INSTANCES"
printf 'point the control plane at it: PATCHAPI_REMEDIATION_WORKER_POOL=%s\n' "$POOL"
printf 'watch it: gcloud beta run worker-pools logs tail %s --region=%s\n' "$POOL" "$REGION"
