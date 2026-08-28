#!/usr/bin/env bash
# Local control plane against Cloud SQL (the same instance Cloud Run uses).
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
# Same job Cloud Run starts. Without this the console writes a FAILED row the
# moment Start remediation is pressed, because nothing is configured to run it.
export PATCHAPI_REMEDIATION_JOB="${PATCHAPI_REMEDIATION_JOB:-patchapi-remediate}"
export DATABASE_URL
DATABASE_URL="$(tr -d '\n' <"$DSN_FILE")"
# A locally dispatched remediation is a child of this process and inherits its
# environment, so anything the Cloud Run job is given has to be given here too.
# Assembling it from whichever shell happened to start the server is how a run
# reached the last step and died on a missing key.
export GOOGLE_API_KEY="${GOOGLE_API_KEY:-$(
  gcloud secrets versions access latest --secret=patchapi-gemini-api-key \
    --project="$GCP_PROJECT" 2>/dev/null || true
)}"
if [[ -z "$GOOGLE_API_KEY" ]]; then
  printf 'warning: no Gemini API key; a locally dispatched run cannot reason\n' >&2
fi

# The remediator opens the pull request through this service, which owns the
# GitHub App key. A local run inherits this variable from here; without it the
# run patches and verifies and then stops on "the GitHub tool service is not
# configured", which reads like a disconnected GitHub App and is not one.
export PATCHAPI_GITHUB_TOOLS_URL="${PATCHAPI_GITHUB_TOOLS_URL:-$(
  gcloud run services describe patchapi-github-tools \
    --project="$GCP_PROJECT" --region="$GCP_REGION" \
    --format='value(status.url)' 2>/dev/null || true
)}"
if [[ -z "$PATCHAPI_GITHUB_TOOLS_URL" ]]; then
  printf 'warning: patchapi-github-tools has no URL; runs will stop before the pull request\n' >&2
fi
export PATCHAPI_CORS_ORIGINS="${PATCHAPI_CORS_ORIGINS:-http://localhost:3000}"
export PATCHAPI_FRONTEND_ORIGIN="${PATCHAPI_FRONTEND_ORIGIN:-http://localhost:3000}"
export PATCHAPI_IDENTITY_ACTION_URL="${PATCHAPI_IDENTITY_ACTION_URL:-http://localhost:3000/auth/action}"
export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8080}"
# patchapi-state is installed as a wheel copy. Without the repo root on
# sys.path, `patchapi-serve` keeps serving yesterday's codebase routes and
# the Codebase tab never sees new `directory` roots.
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec uv run --package patchapi-state patchapi-serve
