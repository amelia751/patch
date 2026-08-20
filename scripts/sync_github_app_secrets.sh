#!/usr/bin/env bash
# Copy local GitHub App credentials into Secret Manager. Values stay in
# `.secrets/` and Secret Manager — this script never prints them.
#
#   ./scripts/sync_github_app_secrets.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT:-patch-505223}"
JSON="$ROOT/.secrets/github-app.json"
PEM="$ROOT/.secrets/github-app.pem"

if [[ ! -f "$JSON" || ! -f "$PEM" ]]; then
  printf 'missing %s or %s\n' "$JSON" "$PEM" >&2
  exit 1
fi

upsert_secret() {
  local name="$1" file="$2"
  if gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets versions add "$name" --project="$PROJECT_ID" --data-file="$file" >/dev/null
    printf 'updated %s\n' "$name"
  else
    gcloud secrets create "$name" \
      --project="$PROJECT_ID" \
      --replication-policy=automatic \
      --data-file="$file" >/dev/null
    printf 'created %s\n' "$name"
  fi
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
chmod 700 "$tmp"

python3 - "$JSON" "$tmp" <<'PY'
import json, sys
from pathlib import Path

src, dest = Path(sys.argv[1]), Path(sys.argv[2])
blob = json.loads(src.read_text(encoding="utf-8"))
fields = {
    "client_id": blob.get("client_id") or blob.get("clientId"),
    "client_secret": blob.get("client_secret") or blob.get("clientSecret"),
    "app_id": blob.get("app_id") or blob.get("appId"),
}
missing = [name for name, value in fields.items() if value is None or str(value).strip() == ""]
if missing:
    raise SystemExit(f"github-app.json missing {', '.join(missing)}")
(dest / "client_id").write_text(str(fields["client_id"]).strip(), encoding="utf-8")
(dest / "client_secret").write_text(str(fields["client_secret"]).strip(), encoding="utf-8")
(dest / "app_id").write_text(str(fields["app_id"]).strip(), encoding="utf-8")
PY

upsert_secret patchapi-github-app "$JSON"
upsert_secret patchapi-github-oauth-client-id "$tmp/client_id"
upsert_secret patchapi-github-oauth-client-secret "$tmp/client_secret"
upsert_secret patchapi-github-app-id "$tmp/app_id"
upsert_secret patchapi-github-app-private-key "$PEM"
