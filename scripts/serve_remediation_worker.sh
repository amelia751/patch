#!/usr/bin/env bash
# The warm remediator, on this machine.
#
# The local counterpart of the Cloud Run worker pool. Started by
# serve_control_api.sh, or run alone in its own terminal to watch a run happen.
#
# Why not a subprocess per run, which is what `PATCHAPI_REMEDIATION_LOCAL=1`
# does: the two waits a remediation used to pay are startup and resume, and a
# subprocess per run pays both. Measured on Cloud Run's task API the deployed job
# waited 136s for capacity and paid it again when an operator hold ended the
# execution. A laptop's fork is far cheaper than that, but it is still a fresh
# process that re-imports the fleet, re-opens Postgres, and cannot be holding an
# ADK session when the operator answers. Running the same worker here means local
# behaviour is evidence about deployed behaviour rather than a different lane
# that happens to produce a pull request.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DSN_FILE="$ROOT/.secrets/database-url-proxy.txt"
if [[ ! -f "$DSN_FILE" ]]; then
  printf 'missing %s — run ./scripts/bootstrap_cloud_sql.sh first\n' "$DSN_FILE" >&2
  exit 1
fi

if ! lsof -nP -iTCP:5433 -sTCP:LISTEN >/dev/null 2>&1; then
  printf 'starting Cloud SQL Auth Proxy on 127.0.0.1:5433\n'
  "$ROOT/scripts/run_cloud_sql_proxy.sh" >/tmp/cloud-sql-proxy.log 2>&1 &
  for _ in $(seq 1 30); do
    if lsof -nP -iTCP:5433 -sTCP:LISTEN >/dev/null 2>&1; then
      break
    fi
    sleep 0.3
  done
fi

export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"
export GCP_PROJECT="${GCP_PROJECT:-patch-505223}"
export GCP_REGION="${GCP_REGION:-us-central1}"
export GCP_VERTEX_LOCATION="${GCP_VERTEX_LOCATION:-global}"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-$GCP_PROJECT}"
export DATABASE_URL
DATABASE_URL="$(tr -d '\n' <"$DSN_FILE")"

# Everything the Cloud Run worker pool is given, given here too. A worker missing
# one of these does not fail at startup — it fails minutes into a run, after the
# patch, which reads as a broken product rather than a missing variable.
export GOOGLE_API_KEY="${GOOGLE_API_KEY:-$(
  gcloud secrets versions access latest --secret=patchapi-gemini-api-key \
    --project="$GCP_PROJECT" 2>/dev/null || true
)}"
if [[ -z "$GOOGLE_API_KEY" ]]; then
  printf 'warning: no Gemini API key; this worker cannot reason\n' >&2
fi

export PATCHAPI_GITHUB_TOOLS_URL="${PATCHAPI_GITHUB_TOOLS_URL:-$(
  gcloud run services describe patchapi-github-tools \
    --project="$GCP_PROJECT" --region="$GCP_REGION" \
    --format='value(status.url)' 2>/dev/null || true
)}"
if [[ -z "$PATCHAPI_GITHUB_TOOLS_URL" ]]; then
  printf 'warning: patchapi-github-tools has no URL; runs will stop before the pull request\n' >&2
fi

export PATCHAPI_EVIDENCE_BASE_URL="${PATCHAPI_EVIDENCE_BASE_URL:-https://patchapi-api-913371146929.us-central1.run.app}"
export PATCHAPI_GKE_PROJECT="${PATCHAPI_GKE_PROJECT:-$GCP_PROJECT}"
export PATCHAPI_GKE_CLUSTER="${PATCHAPI_GKE_CLUSTER:-patchapi-dev-agentsandbox}"
export PATCHAPI_GKE_LOCATION="${PATCHAPI_GKE_LOCATION:-us-central1-a}"
export PATCHAPI_SANDBOX_NAMESPACE="${PATCHAPI_SANDBOX_NAMESPACE:-patchapi-sandbox-dev}"
export PATCHAPI_REPO_ROOT="${PATCHAPI_REPO_ROOT:-$ROOT}"
export PATCHAPI_FEED_DIR="${PATCHAPI_FEED_DIR:-$ROOT/demo/fixtures}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
# The image sets this; a laptop redirecting to a file does not, and Python then
# block-buffers stdout. A whole run's log stayed inside the process while the
# console showed the run finishing, which reads as a worker that never woke up.
export PYTHONUNBUFFERED=1

# `gke` unless told otherwise, the same as a deployment: this lane runs code a
# model wrote, and the isolation is the reason it is allowed to run at all.
# `PATCHAPI_SANDBOX=local` is the temp-workspace fallback for a machine with no
# cluster access, and it is a weaker boundary — set it deliberately or not at all.
printf 'sandbox: %s\n' "${PATCHAPI_SANDBOX:-gke}"

exec uv run --package patchapi-agent-runner patchapi-remediation-worker
