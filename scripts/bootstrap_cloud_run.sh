#!/usr/bin/env bash
# Reserve the Cloud Run URLs and the GitHub → Artifact Registry deploy path.
#
# Idempotent. Does not apply Terraform (that remains APPLY_INFRA=1). These two
# services are public console endpoints; the Terraform Cloud Run module stays
# closed-ingress for github-tools / repo-indexer.
#
# Service names are the URL. Do not rename them.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
PROJECT_NUMBER="${GCP_PROJECT_NUMBER:-913371146929}"
REGION="${GCP_REGION:-us-central1}"
AR_REPO="${PATCHAPI_AR_REPO:-patchapi}"
GITHUB_REPO="${PATCHAPI_GITHUB_REPO:-amelia751/patch}"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"

WEB_SERVICE=patchapi-web
API_SERVICE=patchapi-api
DEPLOY_SA_ID=patchapi-github-deploy
WEB_SA_ID=patchapi-web
API_SA_ID=patchapi-api
POOL_ID=github-actions
PROVIDER_ID=github
HELLO_IMAGE=us-docker.pkg.dev/cloudrun/container/hello

if [[ ! -f "$KEY_FILE" ]]; then
  printf 'missing service-account key: %s\n' "$KEY_FILE" >&2
  exit 1
fi

export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$KEY_FILE"
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

sa_email() {
  printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT_ID"
}

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

ensure_secret() {
  local name="$1" file="$2"
  if ! gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$name" \
      --project="$PROJECT_ID" \
      --replication-policy=automatic
    gcloud secrets versions add "$name" --project="$PROJECT_ID" --data-file="$file"
  fi
}

ensure_secret_value() {
  local name="$1" value="$2"
  local tmp
  tmp="$(mktemp)"
  printf '%s' "$value" >"$tmp"
  chmod 600 "$tmp"
  ensure_secret "$name" "$tmp"
  rm -f "$tmp"
}

bind_project_role() {
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$1" \
    --role="$2" \
    --condition=None \
    --quiet >/dev/null
}

printf 'enabling APIs\n'
ensure_api run.googleapis.com
ensure_api artifactregistry.googleapis.com
ensure_api iam.googleapis.com
ensure_api iamcredentials.googleapis.com
ensure_api sts.googleapis.com
ensure_api secretmanager.googleapis.com
ensure_api identitytoolkit.googleapis.com

printf 'service accounts\n'
ensure_sa "$DEPLOY_SA_ID" "GitHub Actions Cloud Run deploy"
ensure_sa "$WEB_SA_ID" "PatchAPI dashboard (Cloud Run)"
ensure_sa "$API_SA_ID" "PatchAPI control plane (Cloud Run)"

DEPLOY_SA="$(sa_email "$DEPLOY_SA_ID")"
WEB_SA="$(sa_email "$WEB_SA_ID")"
API_SA="$(sa_email "$API_SA_ID")"

bind_project_role "$DEPLOY_SA" roles/run.admin
bind_project_role "$DEPLOY_SA" roles/artifactregistry.writer
bind_project_role "$DEPLOY_SA" roles/secretmanager.secretAccessor
bind_project_role "$API_SA" roles/secretmanager.secretAccessor
# Create / rotate / delete patchapi-ps-* and patchapi-gcp-* payloads. Reveal
# stays on secretAccessor.
#
# setIamPolicy is here because the identity that stores a credential is not the
# one that uses it: the console writes the secret, the remediation job reads it
# during live verification. Granting the job blanket access to the project's
# secrets would hand it the database URL and the GitHub App key, so instead the
# console binds the reader on each secret it creates, which needs this.
VAULT_ROLE=projects/${PROJECT_ID}/roles/patchapiSecretVault
VAULT_PERMS=secretmanager.secrets.create,secretmanager.secrets.delete,secretmanager.secrets.get,secretmanager.versions.add,secretmanager.secrets.getIamPolicy,secretmanager.secrets.setIamPolicy
if gcloud iam roles describe patchapiSecretVault --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam roles update patchapiSecretVault \
    --project="$PROJECT_ID" \
    --permissions="$VAULT_PERMS" \
    --quiet >/dev/null
else
  gcloud iam roles create patchapiSecretVault \
    --project="$PROJECT_ID" \
    --title="PatchAPI secret vault" \
    --description="Create, rotate, and delete PatchAPI-managed Secret Manager payloads." \
    --permissions="$VAULT_PERMS"
fi
bind_project_role "$API_SA" "$VAULT_ROLE"
bind_project_role "$API_SA" roles/logging.logWriter
bind_project_role "$API_SA" roles/firebaseauth.admin
bind_project_role "$WEB_SA" roles/logging.logWriter

gcloud iam service-accounts add-iam-policy-binding "$WEB_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role=roles/iam.serviceAccountUser \
  --quiet >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$API_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role=roles/iam.serviceAccountUser \
  --quiet >/dev/null

printf 'artifact registry %s\n' "$AR_REPO"
if ! gcloud artifacts repositories describe "$AR_REPO" \
  --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPO" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --repository-format=docker \
    --description="PatchAPI Cloud Run images (web + api)"
fi
gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role=roles/artifactregistry.writer \
  --quiet >/dev/null
gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@serverless-robot-prod.iam.gserviceaccount.com" \
  --role=roles/artifactregistry.reader \
  --quiet >/dev/null

printf 'workload identity federation for %s\n' "$GITHUB_REPO"
if ! gcloud iam workload-identity-pools describe "$POOL_ID" \
  --project="$PROJECT_ID" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL_ID" \
    --project="$PROJECT_ID" \
    --location=global \
    --display-name="GitHub Actions"
fi
if ! gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --project="$PROJECT_ID" \
  --location=global \
  --workload-identity-pool="$POOL_ID" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --project="$PROJECT_ID" \
    --location=global \
    --workload-identity-pool="$POOL_ID" \
    --display-name="GitHub" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'"
fi

WIF_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPO}"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --project="$PROJECT_ID" \
  --member="$WIF_MEMBER" \
  --role=roles/iam.workloadIdentityUser \
  --quiet >/dev/null

printf 'secrets\n'
ensure_secret patchapi-session-secret "$ROOT/.secrets/session_secret.txt"
ensure_secret patchapi-identity-api-key "$ROOT/.secrets/identity_platform_api_key.txt"

GOOGLE_OAUTH="$ROOT/.secrets/google-oauth.json"
CLIENT_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["web"]["client_id"], end="")' "$GOOGLE_OAUTH")"
CLIENT_SECRET="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["web"]["client_secret"], end="")' "$GOOGLE_OAUTH")"
ensure_secret_value patchapi-google-oauth-client-id "$CLIENT_ID"
ensure_secret_value patchapi-google-oauth-client-secret "$CLIENT_SECRET"
ensure_secret_value patchapi-database-url "unset"
if [[ -f "$ROOT/.secrets/github-app.json" && -f "$ROOT/.secrets/github-app.pem" ]]; then
  "$ROOT/scripts/sync_github_app_secrets.sh"
fi

printf 'reserving Cloud Run services\n'
deploy_hello() {
  local name="$1" sa="$2"
  if gcloud run services describe "$name" --project="$PROJECT_ID" --region="$REGION" >/dev/null 2>&1; then
    printf '  %s already exists\n' "$name"
    return 0
  fi
  gcloud run deploy "$name" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --image="$HELLO_IMAGE" \
    --service-account="$sa" \
    --allow-unauthenticated \
    --ingress=all \
    --port=8080 \
    --memory=512Mi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=1 \
    --quiet
}

deploy_hello "$WEB_SERVICE" "$WEB_SA"
deploy_hello "$API_SERVICE" "$API_SA"

WEB_URL="$(gcloud run services describe "$WEB_SERVICE" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')"
API_URL="$(gcloud run services describe "$API_SERVICE" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')"
WEB_URL_STABLE="https://${WEB_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
API_URL_STABLE="https://${API_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"

printf 'authorized Identity Platform domains\n'
TOKEN="$(gcloud auth print-access-token)"
python3 - "$TOKEN" "$PROJECT_ID" "$WEB_URL" "$API_URL" "$WEB_URL_STABLE" "$API_URL_STABLE" <<'PY'
import json, sys, urllib.request

token, project, *urls = sys.argv[1:]
hosts = []
for url in urls:
    host = url.split("://", 1)[-1].split("/", 1)[0]
    if host and host not in hosts:
        hosts.append(host)

req = urllib.request.Request(
    f"https://identitytoolkit.googleapis.com/admin/v2/projects/{project}/config",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as resp:
    config = json.load(resp)
domains = list(config.get("authorizedDomains") or [])
changed = False
for host in hosts:
    if host not in domains:
        domains.append(host)
        changed = True
if not changed:
    sys.exit(0)
body = json.dumps({"authorizedDomains": domains}).encode()
patch = urllib.request.Request(
    f"https://identitytoolkit.googleapis.com/admin/v2/projects/{project}/config?updateMask=authorizedDomains",
    data=body,
    method="PATCH",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
)
urllib.request.urlopen(patch).read()
PY

cat <<EOF

Cloud Run URLs (stable while these service names exist):
  frontend  ${WEB_URL_STABLE}
            ${WEB_URL}
  backend   ${API_URL_STABLE}
            ${API_URL}

Add these to the Web OAuth client in Google Cloud Console
(APIs & Services → Credentials → the Web client). A service account
cannot edit that client on a no-org project:
  JavaScript origin     ${WEB_URL_STABLE}
  Redirect URI          ${API_URL_STABLE}/api/auth/google/callback

GitHub Actions on push to main deploys to these names. The API image
stays on the placeholder until Secret Manager patchapi-database-url
is a real postgres:// DSN (Cloud SQL is not provisioned; Terraform
ties it to the GKE VPC).

WIF provider:
  projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}
EOF
