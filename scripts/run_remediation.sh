#!/usr/bin/env bash
# One remediation, run the way Cloud Run runs it, on this machine.
#
# The Cloud Run job's command is `patchapi-remediate --run-id <uuid>`. This is
# the same command with the environment the job gets from Cloud Run assembled
# from `.secrets/` instead: Cloud SQL through the Auth Proxy, and Application
# Default Credentials pointing at the service account, which is what the sandbox
# uses to write its kubeconfig and what Vertex uses to answer the agents.
#
#   ./scripts/run_remediation.sh <run-id>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  printf 'usage: %s <run-id>\n' "$0" >&2
  exit 2
fi

DSN_FILE="$ROOT/.secrets/database-url-proxy.txt"
if [[ ! -f "$DSN_FILE" ]]; then
  printf 'missing %s — run ./scripts/bootstrap_cloud_sql.sh first\n' "$DSN_FILE" >&2
  exit 2
fi

if ! lsof -nP -iTCP:5433 -sTCP:LISTEN >/dev/null 2>&1; then
  printf 'starting Cloud SQL Auth Proxy on 127.0.0.1:5433\n'
  "$ROOT/scripts/run_cloud_sql_proxy.sh" >/tmp/cloud-sql-proxy.log 2>&1 &
  for _ in $(seq 1 30); do
    if lsof -nP -iTCP:5433 -sTCP:LISTEN >/dev/null 2>&1; then break; fi
    sleep 0.3
  done
fi

export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"
export GCP_PROJECT="${GCP_PROJECT:-patch-505223}"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-$GCP_PROJECT}"
export DATABASE_URL
DATABASE_URL="$(tr -d '\n' <"$DSN_FILE")"

# The agents read the same configuration the deployed runner does.
if [[ -f "$ROOT/.secrets/gemini_api_key.txt" ]]; then
  GEMINI_API_KEY="$(tr -d '\n' <"$ROOT/.secrets/gemini_api_key.txt")"
  export GEMINI_API_KEY
  export GOOGLE_API_KEY="${GOOGLE_API_KEY:-$GEMINI_API_KEY}"
fi

# The PR leg, if ./scripts/run_github_tools.sh is up. Left unset otherwise, so a
# run without it refuses to open a pull request rather than failing obscurely.
# Probed by connecting rather than with lsof, which lives in /usr/sbin and is
# not on every PATH — a missing probe tool silently cost a run its PR stage.
if (exec 3<>/dev/tcp/127.0.0.1/8081) 2>/dev/null; then
  export PATCHAPI_GITHUB_TOOLS_URL="${PATCHAPI_GITHUB_TOOLS_URL:-http://127.0.0.1:8081}"
fi

# Locally the control plane on 8080 serves the same evidence route Cloud Run
# does, so a snapshot cited by a local run is a link that resolves here too.
export PATCHAPI_EVIDENCE_BASE_URL="${PATCHAPI_EVIDENCE_BASE_URL:-http://127.0.0.1:8080}"

export PYTHONUNBUFFERED=1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec uv run --package patchapi-agent-runner patchapi-remediate --run-id "$1"
