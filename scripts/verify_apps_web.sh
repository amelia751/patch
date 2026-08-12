#!/usr/bin/env bash
# Dynamic verifier for the apps/web dashboard tree (setup.md T-apps-web).
# Proves the tree is real: clean install from the lockfile, lint, production
# build, then an HTTP probe against a server this script starts and stops.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${REPO_ROOT}/apps/web"
DEFAULT_PORT=3000
if [[ -n "${PORT:-}" ]]; then
  PORT_WAS_EXPLICIT=1
else
  PORT_WAS_EXPLICIT=0
fi
PORT="${PORT:-${DEFAULT_PORT}}"
HOST="127.0.0.1"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-90}"

SERVER_PID=""
LOG_FILE=""

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

cleanup() {
  local status=$?
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "${SERVER_PID}" 2>/dev/null || break
      sleep 0.5
    done
    kill -9 "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  if [[ $status -ne 0 && -n "${LOG_FILE}" && -s "${LOG_FILE}" ]]; then
    echo "--- next start log ---" >&2
    tail -40 "${LOG_FILE}" >&2
  fi
  if [[ -n "${LOG_FILE}" ]]; then
    rm -f "${LOG_FILE}"
  fi
  return $status
}
trap cleanup EXIT

port_in_use() {
  # A pre-existing listener would make the HTTP probe test someone else's
  # server, so refuse to run rather than report a false PASS.
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1
}

echo "== apps/web verifier =="
echo "repo:  ${REPO_ROOT}"
echo "app:   ${APP_DIR}"
echo "port:  ${PORT}"

[[ -d "${APP_DIR}" ]] || fail "apps/web does not exist"
[[ -f "${APP_DIR}/package-lock.json" ]] || fail "apps/web/package-lock.json missing (this tree is npm, not pnpm/yarn)"

for foreign in pnpm-lock.yaml yarn.lock bun.lockb; do
  if [[ -e "${APP_DIR}/${foreign}" ]]; then
    fail "unexpected ${foreign} in apps/web; this tree uses npm"
  fi
done

if [[ -d "${REPO_ROOT}/web" ]]; then
  fail "root web/ still exists; it must be relocated to apps/web"
fi

command -v node >/dev/null 2>&1 || fail "node not on PATH"
command -v npm >/dev/null 2>&1 || fail "npm not on PATH"
command -v curl >/dev/null 2>&1 || fail "curl not on PATH"
echo "node:  $(node --version)"
echo "npm:   $(npm --version)"

if port_in_use; then
  if (( PORT_WAS_EXPLICIT )); then
    fail "port ${PORT} is already in use; free it or re-run with a different PORT"
  fi
  # Sibling fleet workers and stray dev servers squat the default port. Move to
  # a free one rather than probing a server this script did not start.
  echo "note:  port ${PORT} is in use by another process; selecting a free port"
  found_port=""
  for candidate in $(seq $((DEFAULT_PORT + 1)) $((DEFAULT_PORT + 50))); do
    if ! lsof -nP -iTCP:"${candidate}" -sTCP:LISTEN >/dev/null 2>&1; then
      found_port="${candidate}"
      break
    fi
  done
  [[ -n "${found_port}" ]] || fail "no free port in ${DEFAULT_PORT}-$((DEFAULT_PORT + 50))"
  PORT="${found_port}"
  echo "port:  ${PORT} (fallback)"
fi

echo
echo "== npm ci =="
npm --prefix "${APP_DIR}" ci

echo
echo "== npm run lint =="
npm --prefix "${APP_DIR}" run lint

echo
echo "== npm run build =="
npm --prefix "${APP_DIR}" run build

echo
echo "== http smoke =="
LOG_FILE="$(mktemp -t patchapi-web-start)"
npm --prefix "${APP_DIR}" start -- --port "${PORT}" --hostname "${HOST}" >"${LOG_FILE}" 2>&1 &
SERVER_PID=$!

http_code=""
deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    fail "next start exited before serving a request"
  fi
  http_code="$(curl -s -o /dev/null -w '%{http_code}' "http://${HOST}:${PORT}/" || true)"
  if [[ "${http_code}" == "200" ]]; then
    break
  fi
  sleep 1
done

[[ "${http_code}" == "200" ]] || fail "GET http://${HOST}:${PORT}/ returned '${http_code:-no response}', expected 200"
echo "GET http://${HOST}:${PORT}/ -> 200"

body_bytes="$(curl -fsS "http://${HOST}:${PORT}/" | wc -c | tr -d ' ')"
(( body_bytes > 0 )) || fail "server returned an empty body"
echo "body: ${body_bytes} bytes"

echo
echo "PASS: apps/web installs, lints, builds, and serves HTTP 200"
