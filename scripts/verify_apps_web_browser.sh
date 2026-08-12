#!/usr/bin/env bash
# Dynamic verifier for the apps/web browser smoke suite (setup.md
# T-apps-web-browser). Boots a real Next.js server on a free port, drives it
# with Playwright/Chromium, asserts a screenshot artifact landed on disk, then
# tears the server down. Nothing here trusts a cached result.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

APP_DIR="${REPO_ROOT}/apps/web"
E2E_DIR="${APP_DIR}/e2e"
ARTIFACT_DIR="${E2E_DIR}/artifacts"
SCREENSHOT="${ARTIFACT_DIR}/home.png"
LEDGER="demo/setup-ledger.ndjson"
COMMAND="./scripts/verify_apps_web_browser.sh"
STATUS="FAIL"

DEFAULT_PORT=3100
if [[ -n "${PORT:-}" ]]; then
  PORT_WAS_EXPLICIT=1
else
  PORT_WAS_EXPLICIT=0
fi
PORT="${PORT:-${DEFAULT_PORT}}"
HOST="127.0.0.1"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-120}"

SERVER_PID=""
LOG_FILE=""

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

record() {
  mkdir -p "$(dirname "${LEDGER}")"
  printf '{"task":"T-apps-web-browser","status":"%s","command":"%s","at":"%s"}\n' \
    "${STATUS}" "${COMMAND}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"${LEDGER}"
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
  if [[ ${status} -ne 0 && -n "${LOG_FILE}" && -s "${LOG_FILE}" ]]; then
    echo "--- next start log ---" >&2
    tail -40 "${LOG_FILE}" >&2
  fi
  if [[ -n "${LOG_FILE}" ]]; then
    rm -f "${LOG_FILE}"
  fi
  record
  return ${status}
}
trap cleanup EXIT

echo "== apps/web browser verifier =="
echo "repo:  ${REPO_ROOT}"
echo "e2e:   ${E2E_DIR}"

[[ -d "${APP_DIR}" ]] || fail "apps/web does not exist"
[[ -f "${E2E_DIR}/package.json" ]] || fail "apps/web/e2e/package.json missing"
[[ -f "${E2E_DIR}/package-lock.json" ]] || fail "apps/web/e2e/package-lock.json missing (this tree is npm)"
[[ -f "${APP_DIR}/playwright.config.ts" ]] || fail "apps/web/playwright.config.ts missing"

for foreign in pnpm-lock.yaml yarn.lock bun.lockb; do
  if [[ -e "${E2E_DIR}/${foreign}" ]]; then
    fail "unexpected ${foreign} in apps/web/e2e; this tree uses npm"
  fi
done

command -v node >/dev/null 2>&1 || fail "node not on PATH"
command -v npm >/dev/null 2>&1 || fail "npm not on PATH"
command -v curl >/dev/null 2>&1 || fail "curl not on PATH"
command -v lsof >/dev/null 2>&1 || fail "lsof not on PATH"
echo "node:  $(node --version)"
echo "npm:   $(npm --version)"

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

if port_in_use "${PORT}"; then
  if (( PORT_WAS_EXPLICIT )); then
    fail "port ${PORT} is already in use; free it or re-run with a different PORT"
  fi
  # Sibling fleet workers squat ports. Probing a server this script did not
  # start would be a false PASS, so move to a free one instead.
  echo "note:  port ${PORT} is in use; selecting a free port"
  found_port=""
  for candidate in $(seq $((DEFAULT_PORT + 1)) $((DEFAULT_PORT + 50))); do
    if ! port_in_use "${candidate}"; then
      found_port="${candidate}"
      break
    fi
  done
  [[ -n "${found_port}" ]] || fail "no free port in ${DEFAULT_PORT}-$((DEFAULT_PORT + 50))"
  PORT="${found_port}"
fi
echo "port:  ${PORT}"

echo
echo "== e2e toolchain =="
npm --prefix "${E2E_DIR}" ci
# Idempotent: a no-op once the pinned Chromium build is in the local cache.
npm --prefix "${E2E_DIR}" run install-browsers

echo
echo "== dashboard build =="
if [[ ! -d "${APP_DIR}/node_modules" ]]; then
  # Only install when nothing is there: `npm ci` wipes node_modules, which
  # would break a sibling worker's running dev server.
  npm --prefix "${APP_DIR}" ci
else
  echo "apps/web/node_modules present; skipping install"
fi
npm --prefix "${APP_DIR}" run build

echo
echo "== boot next =="
LOG_FILE="$(mktemp -t patchapi-web-browser)"
npm --prefix "${APP_DIR}" start -- --port "${PORT}" --hostname "${HOST}" >"${LOG_FILE}" 2>&1 &
SERVER_PID=$!

http_code=""
deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    fail "next start exited before serving a request"
  fi
  http_code="$(curl -s -o /dev/null -w '%{http_code}' "http://${HOST}:${PORT}/" || true)"
  [[ "${http_code}" == "200" ]] && break
  sleep 1
done
[[ "${http_code}" == "200" ]] || fail "GET http://${HOST}:${PORT}/ returned '${http_code:-no response}', expected 200"
echo "GET http://${HOST}:${PORT}/ -> 200"

echo
echo "== playwright =="
# Stale artifacts would let a failed run report a screenshot it never took.
rm -rf "${ARTIFACT_DIR}"
mkdir -p "${ARTIFACT_DIR}"

PLAYWRIGHT_BASE_URL="http://${HOST}:${PORT}" \
  npm --prefix "${E2E_DIR}" run test

[[ -s "${SCREENSHOT}" ]] || fail "expected screenshot artifact at ${SCREENSHOT}"
magic="$(od -An -tx1 -N4 "${SCREENSHOT}" | tr -d ' \n')"
if [[ "${magic}" != "89504e47" ]]; then
  fail "${SCREENSHOT} is not a PNG (magic ${magic})"
fi
echo "screenshot: ${SCREENSHOT} ($(wc -c <"${SCREENSHOT}" | tr -d ' ') bytes)"

STATUS="PASS"
echo
echo "PASS: apps/web serves a real page and the Playwright smoke suite drove it in Chromium"
