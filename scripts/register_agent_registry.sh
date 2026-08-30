#!/usr/bin/env bash
# Publish the PatchAPI fleet to Google Agent Registry.
#
# The catalog answers "which agents does this enterprise run, and what does each
# one claim it can do" from the platform rather than from a slide. Cards are
# derived from `agents/config.py` by `agents/catalog.py`, so a published version
# or skill cannot drift from the tool grants in the code.
#
# There is no Terraform resource for an Agent Registry Service in
# `hashicorp/google`, so the resources themselves are created here. Terraform
# owns the API enablement and the IAM (infra/terraform/environments/dev).
#
# Idempotent: a second run patches every existing Service instead of failing.
#
#   ./scripts/register_agent_registry.sh              # publish, then read back
#   ./scripts/register_agent_registry.sh --dry-run    # print the cards only
#   ./scripts/register_agent_registry.sh --verify-only
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
REGION="${PATCHAPI_REGISTRY_LOCATION:-us-central1}"
AGENTS_SERVICE="${PATCHAPI_AGENTS_SERVICE:-patchapi-agents}"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"

if [[ -f "$KEY_FILE" ]]; then
  export GOOGLE_APPLICATION_CREDENTIALS="$KEY_FILE"
  export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$KEY_FILE"
else
  printf 'no key file at %s; falling back to the ambient gcloud credentials\n' "$KEY_FILE" >&2
fi
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1
export GCP_PROJECT="$PROJECT_ID"
export PATCHAPI_REGISTRY_LOCATION="$REGION"
export PATCHAPI_REGISTRY_ENABLED=1

# The cards advertise where each agent answers, so the origin has to be real.
# Resolved from Cloud Run rather than pinned: the URL carries a project-specific
# hash that a clean account would not reproduce.
if [[ -z "${PATCHAPI_A2A_BASE_URL:-}" ]]; then
  PATCHAPI_A2A_BASE_URL="$(
    gcloud run services describe "$AGENTS_SERVICE" \
      --project="$PROJECT_ID" --region="$REGION" \
      --format='value(status.url)' 2>/dev/null || true
  )"
fi
if [[ -z "$PATCHAPI_A2A_BASE_URL" ]]; then
  printf 'cannot resolve an A2A base URL: Cloud Run service %s is not deployed in %s.\n' \
    "$AGENTS_SERVICE" "$REGION" >&2
  printf 'Deploy the agent lane first, or set PATCHAPI_A2A_BASE_URL explicitly.\n' >&2
  exit 1
fi
export PATCHAPI_A2A_BASE_URL

# Registered only when a JSON-RPC endpoint exists. Agent Registry rejects an MCP
# Server whose interface is not JSONRPC, so a REST tool service cannot stand in.
if [[ -n "${PATCHAPI_MCP_URL:-}" ]]; then
  export PATCHAPI_MCP_URL
fi

gcloud services enable agentregistry.googleapis.com --project="$PROJECT_ID" >/dev/null

printf 'project   %s\n' "$PROJECT_ID"
printf 'location  %s\n' "$REGION"
printf 'a2a base  %s\n' "$PATCHAPI_A2A_BASE_URL"
printf 'mcp url   %s\n' "${PATCHAPI_MCP_URL:-<unset: MCP registration skipped>}"
printf '\n'

export PYTHONUNBUFFERED=1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec uv run python "$ROOT/scripts/register_agent_registry.py" "$@"
