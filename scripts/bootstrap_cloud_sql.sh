#!/usr/bin/env bash
# Cheap console Cloud SQL — not the Terraform GKE-VPC instance.
#
# Terraform `enable_cloud_sql` peers private IP into the sandbox GKE VPC, which
# means paying for a cluster. This instance is a shared-core Postgres 16 with a
# public IP that has no authorized networks: Cloud Run reaches it through the
# Cloud SQL Auth Connector (Unix socket), not the internet.
#
# Instance name: patchapi-console
# Connection:    patch-505223:us-central1:patchapi-console
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
REGION="${GCP_REGION:-us-central1}"
INSTANCE="${PATCHAPI_CLOUDSQL_INSTANCE:-patchapi-console}"
DATABASE="${PATCHAPI_DB_NAME:-patchapi}"
DB_USER="${PATCHAPI_DB_USER:-patchapi}"
TIER="${PATCHAPI_CLOUDSQL_TIER:-db-f1-micro}"
KEY_FILE="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/.secrets/gcp-service-account.json}"
API_SA="patchapi-api@${PROJECT_ID}.iam.gserviceaccount.com"
CONNECTION_NAME="${PROJECT_ID}:${REGION}:${INSTANCE}"

if [[ ! -f "$KEY_FILE" ]]; then
  printf 'missing service-account key: %s\n' "$KEY_FILE" >&2
  exit 1
fi

export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="$KEY_FILE"
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

ensure_api() {
  gcloud services enable "$1" --project="$PROJECT_ID"
}

printf 'enabling SQL Admin API\n'
ensure_api sqladmin.googleapis.com

if gcloud sql instances describe "$INSTANCE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  printf 'instance %s already exists\n' "$INSTANCE"
else
  printf 'creating %s (%s, zonal, 10 GB) — several minutes\n' "$INSTANCE" "$TIER"
  ROOT_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  gcloud sql instances create "$INSTANCE" \
    --project="$PROJECT_ID" \
    --database-version=POSTGRES_16 \
    --edition=enterprise \
    --tier="$TIER" \
    --region="$REGION" \
    --availability-type=ZONAL \
    --storage-size=10 \
    --storage-type=SSD \
    --storage-auto-increase \
    --assign-ip \
    --backup-start-time=07:00 \
    --maintenance-window-day=SUN \
    --maintenance-window-hour=7 \
    --root-password="$ROOT_PASS" \
    --database-flags=cloudsql.iam_authentication=on \
    --deletion-protection
fi

if ! gcloud sql databases describe "$DATABASE" --instance="$INSTANCE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud sql databases create "$DATABASE" --instance="$INSTANCE" --project="$PROJECT_ID"
fi

APP_PASS_FILE="$ROOT/.secrets/cloud-sql-password.txt"
if [[ ! -f "$APP_PASS_FILE" ]]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(24))' >"$APP_PASS_FILE"
  chmod 600 "$APP_PASS_FILE"
fi
APP_PASS="$(tr -d '\n' <"$APP_PASS_FILE")"

if gcloud sql users list --instance="$INSTANCE" --project="$PROJECT_ID" --format='value(name)' | grep -qx "$DB_USER"; then
  gcloud sql users set-password "$DB_USER" \
    --instance="$INSTANCE" \
    --project="$PROJECT_ID" \
    --password="$APP_PASS"
else
  gcloud sql users create "$DB_USER" \
    --instance="$INSTANCE" \
    --project="$PROJECT_ID" \
    --password="$APP_PASS"
fi

# Cloud Run DSN: Unix socket the Auth Connector mounts. No public IP in the URL.
CLOUD_DSN="postgresql://${DB_USER}:${APP_PASS}@/${DATABASE}?host=/cloudsql/${CONNECTION_NAME}"
# Local DSN: Auth Proxy on 127.0.0.1:5433 (see README).
LOCAL_DSN="postgresql://${DB_USER}:${APP_PASS}@127.0.0.1:5433/${DATABASE}"

printf '%s\n' "$CLOUD_DSN" >"$ROOT/.secrets/database-url-cloud.txt"
printf '%s\n' "$LOCAL_DSN" >"$ROOT/.secrets/database-url-proxy.txt"
chmod 600 "$ROOT/.secrets/database-url-cloud.txt" "$ROOT/.secrets/database-url-proxy.txt"

python3 - "$CONNECTION_NAME" "$INSTANCE" "$REGION" "$ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[4])
path = root / ".secrets" / "cloud-sql.json"
path.write_text(
    json.dumps({
        "instance": sys.argv[2],
        "connection_name": sys.argv[1],
        "region": sys.argv[3],
        "database": "patchapi",
        "user": "patchapi",
        "tier": "db-f1-micro",
        "note": "Standalone console instance. Not the Terraform GKE-VPC Cloud SQL.",
    }, indent=2) + "\n",
    encoding="utf-8",
)
path.chmod(0o600)
PY

TMP="$(mktemp)"
printf '%s' "$CLOUD_DSN" >"$TMP"
chmod 600 "$TMP"
if gcloud secrets describe patchapi-database-url --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets versions add patchapi-database-url --project="$PROJECT_ID" --data-file="$TMP"
else
  gcloud secrets create patchapi-database-url --project="$PROJECT_ID" --replication-policy=automatic
  gcloud secrets versions add patchapi-database-url --project="$PROJECT_ID" --data-file="$TMP"
fi
rm -f "$TMP"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${API_SA}" \
  --role="roles/cloudsql.client" \
  --condition=None \
  --quiet >/dev/null

cat <<EOF

Cloud SQL (console, not GKE-VPC):
  instance         ${INSTANCE}
  connection name  ${CONNECTION_NAME}
  tier             ${TIER} zonal 10 GB
  Secret Manager   patchapi-database-url  (Cloud Run Unix-socket DSN)
  local proxy DSN  .secrets/database-url-proxy.txt

Migrate through the Auth Proxy (do not authorize 0.0.0.0/0):
  cloud-sql-proxy ${CONNECTION_NAME} --port=5433
  DATABASE_URL=\$(cat .secrets/database-url-proxy.txt) PYTHONPATH=db/src uv run python -m patchapi_db migrate

EOF
