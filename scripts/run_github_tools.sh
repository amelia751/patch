#!/usr/bin/env bash
# Local GitHub tool service. Owns the App key; agents never see it.
#
# Discovers the amelia751 installation from the App JWT. Does not write
# credentials into the repository.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PATCHAPI_GITHUB_TOOLS_PORT:-8081}"
APP_JSON="${GITHUB_APP_JSON:-$ROOT/.secrets/github-app.json}"
PEM="${GITHUB_APP_PRIVATE_KEY_PATH:-$ROOT/.secrets/github-app.pem}"

if [[ ! -f "$APP_JSON" || ! -f "$PEM" ]]; then
  printf 'missing GitHub App files under .secrets/\n' >&2
  exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  printf 'github-tools already listening on 127.0.0.1:%s\n' "$PORT"
  exit 0
fi

export GITHUB_APP_PRIVATE_KEY_PATH="$PEM"
export GITHUB_APP_ID
GITHUB_APP_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["app_id"])' "$APP_JSON")"
export GITHUB_APP_INSTALLATION_ID
GITHUB_APP_INSTALLATION_ID="$(
  cd "$ROOT"
  uv run --package patchapi-auth python - <<'PY'
import asyncio
from packages.auth.config import load_config
from packages.auth.github_oauth import find_installation_for_login

async def main() -> None:
    found = await find_installation_for_login(load_config(), "amelia751")
    if found is None:
        raise SystemExit("no GitHub App installation for amelia751")
    print(found[0])

asyncio.run(main())
PY
)"

printf 'github-tools on 127.0.0.1:%s (installation %s)\n' "$PORT" "$GITHUB_APP_INSTALLATION_ID"
cd "$ROOT"
exec uv run --package patchapi-github-tools uvicorn patchapi_github_tools.asgi:app \
  --host 127.0.0.1 --port "$PORT"
