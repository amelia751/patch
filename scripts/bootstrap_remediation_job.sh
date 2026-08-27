#!/usr/bin/env bash
# The Cloud Run job that performs one remediation.
#
# A job rather than a request handler, for a reason that is not stylistic: a
# remediation reads a repository, opens a GKE sandbox, runs a model through a
# patch loop, builds, tests, verifies, and opens a pull request. That is minutes
# of work. A Pub/Sub push subscription has a hard 600-second ack deadline, so a
# handler doing this would be redelivered mid-patch and the same change would be
# remediated twice. The console's POST writes the run row, returns immediately,
# and starts this; the row is unique per change and repository, so pressing the
# button twice rejoins one run instead of opening two pull requests.
#
# The job's identity is narrow by construction. It reads Cloud SQL, claims
# sandboxes in one GKE namespace, and reaches Vertex. It has no Pub/Sub role, no
# Secret Manager write, no GitHub credential — pull requests are opened through
# the github-tools service, which holds the app key and exposes no merge, no
# admin, and no branch-protection call.
#
# Idempotent. Re-run after any image change to repoint the job at a new tag.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
REGION="${GCP_REGION:-us-central1}"
JOB="${PATCHAPI_REMEDIATION_JOB:-patchapi-remediate}"
RUN_SA_ID="${PATCHAPI_REMEDIATION_SA:-patchapi-remediate}"
API_SA_ID="${PATCHAPI_API_SA:-patchapi-api}"
INVOKER_ROLE_ID="${PATCHAPI_REMEDIATION_INVOKER_ROLE:-patchapiRemediationInvoker}"
SQL_INSTANCE="${PATCHAPI_SQL_INSTANCE:-${PROJECT_ID}:${REGION}:patchapi-console}"
IMAGE_TAG="${PATCHAPI_IMAGE_TAG:-$(git rev-parse HEAD)}"
IMAGE="${PATCHAPI_AGENTS_IMAGE:-${REGION}-docker.pkg.dev/${PROJECT_ID}/patchapi/agents:${IMAGE_TAG}}"
GKE_CLUSTER="${PATCHAPI_GKE_CLUSTER:-patchapi-dev-agentsandbox}"
GKE_LOCATION="${PATCHAPI_GKE_LOCATION:-us-central1-a}"
SANDBOX_NAMESPACE="${PATCHAPI_SANDBOX_NAMESPACE:-patchapi-sandbox-dev}"
GITHUB_TOOLS_URL="${PATCHAPI_GITHUB_TOOLS_URL:-https://patchapi-github-tools-uhkx74fgmq-uc.a.run.app}"
GITHUB_TOOLS_SERVICE="${PATCHAPI_GITHUB_TOOLS_SERVICE:-patchapi-github-tools}"
# Where a captured provider page can be fetched and re-hashed. Set so the
# snapshots a pull request cites are links a reviewer can open, rather than a
# file:// path inside a container that no longer exists by the time they read it.
EVIDENCE_BASE_URL="${PATCHAPI_EVIDENCE_BASE_URL:-https://patchapi-api-913371146929.us-central1.run.app}"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"

# A remediation is minutes of model turns and sandbox commands. Cloud Run jobs
# allow up to 24h; an hour is generous for one repository and still short enough
# that a wedged run surfaces as a failure the same morning.
TASK_TIMEOUT="${PATCHAPI_REMEDIATION_TIMEOUT:-3600}"

if [[ -f "$KEY_FILE" ]]; then
  export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$KEY_FILE"
fi
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

sa_email() {
  printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT_ID"
}

RUN_SA="$(sa_email "$RUN_SA_ID")"
API_SA="$(sa_email "$API_SA_ID")"

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

for api in run.googleapis.com container.googleapis.com aiplatform.googleapis.com; do
  gcloud services enable "$api" --project="$PROJECT_ID"
done

ensure_sa "$RUN_SA_ID" "PatchAPI remediation job"

# Cloud SQL for the run record, Vertex for the agents, logs for the operator.
# `container.developer` is what lets the job write its own kubeconfig from
# application default credentials and create a SandboxClaim; it is granted at
# the project because GKE's cluster-level roles are not namespace-scoped, and
# the namespace boundary is enforced by the cluster's RBAC and NetworkPolicies.
for role in roles/cloudsql.client roles/aiplatform.user roles/logging.logWriter \
            roles/container.developer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${RUN_SA}" --role="$role" --condition=None --quiet >/dev/null
done

# CI repoints this job at each new image, which counts as running Cloud Run as
# the job's identity.
gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$(sa_email "${PATCHAPI_DEPLOY_SA:-patchapi-github-deploy}")" \
  --role=roles/iam.serviceAccountUser --quiet >/dev/null

for secret in patchapi-database-url patchapi-gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --project="$PROJECT_ID" --member="serviceAccount:${RUN_SA}" \
    --role=roles/secretmanager.secretAccessor --quiet >/dev/null
done

# The tool service is deployed private. The job authenticates to it with a
# Google-signed ID token for its own identity, so it needs the invoker role the
# way the agents service already has it.
if [[ -n "$GITHUB_TOOLS_URL" ]]; then
  gcloud run services add-iam-policy-binding "$GITHUB_TOOLS_SERVICE" \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:${RUN_SA}" --role=roles/run.invoker --quiet >/dev/null
fi

ENV_VARS="GCP_PROJECT=${PROJECT_ID}"
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

JOB_ARGS=(
  --project="$PROJECT_ID"
  --region="$REGION"
  --image="$IMAGE"
  --service-account="$RUN_SA"
  --set-cloudsql-instances="$SQL_INSTANCE"
  --set-env-vars="$ENV_VARS"
  --set-secrets="DATABASE_URL=patchapi-database-url:latest,GOOGLE_API_KEY=patchapi-gemini-api-key:latest"
  --command=patchapi-remediate
  # One attempt. A remediation is not idempotent from Cloud Run's point of view
  # — it opens sandboxes and can open a pull request — so a retry is a decision
  # for the operator looking at why the first one stopped, not for the platform.
  --max-retries=0
  --task-timeout="$TASK_TIMEOUT"
  --memory=4Gi
  --cpu=2
)
if gcloud run jobs describe "$JOB" --project="$PROJECT_ID" --region="$REGION" >/dev/null 2>&1; then
  gcloud run jobs update "$JOB" "${JOB_ARGS[@]}" --quiet
else
  gcloud run jobs create "$JOB" "${JOB_ARGS[@]}" --quiet
fi

# One deployed job serves every run because the run id arrives as a container
# override, and overriding args needs `run.jobs.runWithOverrides` —  which
# `roles/run.invoker` does not carry, so the invoker role alone produces a 403
# that looks like the job is missing. The predefined role that does carry it,
# `roles/run.developer`, would also let the control plane update and delete the
# job. Starting a remediation is the whole capability, so it gets a role that is
# only that.
if ! gcloud iam roles describe "$INVOKER_ROLE_ID" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam roles create "$INVOKER_ROLE_ID" --project="$PROJECT_ID" \
    --title="PatchAPI remediation invoker" \
    --description="Start the remediation job with a run id. No update, no delete." \
    --permissions=run.jobs.run,run.jobs.runWithOverrides \
    --stage=GA --quiet >/dev/null
fi

# Scoped to this one job. The control plane starts remediations and must not be
# able to execute anything else Cloud Run holds.
gcloud run jobs add-iam-policy-binding "$JOB" \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:${API_SA}" \
  --role="projects/${PROJECT_ID}/roles/${INVOKER_ROLE_ID}" --quiet >/dev/null

# The laptop API uses the same job. Its identity is the key file, not the
# Cloud Run API SA; without this binding, Start remediation on localhost
# writes a FAILED row the moment the console asks Cloud Run to start work.
if [[ -f "$KEY_FILE" ]]; then
  LOCAL_SA="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['client_email'])" "$KEY_FILE")"
  if [[ -n "$LOCAL_SA" && "$LOCAL_SA" != "$API_SA" ]]; then
    gcloud run jobs add-iam-policy-binding "$JOB" \
      --project="$PROJECT_ID" --region="$REGION" \
      --member="serviceAccount:${LOCAL_SA}" \
      --role="projects/${PROJECT_ID}/roles/${INVOKER_ROLE_ID}" --quiet >/dev/null
  fi
fi

printf 'job %s -> %s\n' "$JOB" "$IMAGE"
printf 'the control plane needs PATCHAPI_REMEDIATION_JOB=%s to dispatch it\n' "$JOB"
printf 'run one by hand: gcloud run jobs execute %s --region=%s --args=--run-id,<uuid> --wait\n' \
  "$JOB" "$REGION"
