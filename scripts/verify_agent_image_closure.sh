#!/usr/bin/env bash
# Does the agent lane image contain everything the agent lane imports?
#
# A checkout answers yes to every import: `PYTHONPATH=.` makes the whole
# repository visible whether a package is declared or copied or not. The image
# is a subset, chosen by the COPY lines in services/agent_runner/Dockerfile, and
# nothing before deploy compares the two. When they diverged, the container
# started, passed its startup probe, claimed a run, and died importing
# `packages.memory` — while a run sat at RECEIVED and the console narrated that
# workers were on the air and free.
#
# So this stages a tree holding only what the Dockerfile copies, resolves it the
# way the Dockerfile does, and imports the entry points from it. Missing files
# and undeclared dependencies both fail here, in seconds, without a daemon.
#
#   ./scripts/verify_agent_image_closure.sh
#
# The staged set below mirrors those COPY lines. Adding one to the Dockerfile
# means adding it here, and the check is worth only as much as that pairing.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
DOCKERFILE="services/agent_runner/Dockerfile"

PACKAGES=(schemas events auth providers state repo_scan policy memory observability)
FULL_SERVICES=(control_api agent_runner)
MANIFEST_ONLY_SERVICES=(repo_indexer)
SOURCE_TREES=(agents sandbox skills)

# The lines this list claims to mirror. A package copied in the image but absent
# here would pass a check that never looked at it.
for package in "${PACKAGES[@]}"; do
  grep -q "^COPY packages/${package} packages/${package}\$" "$DOCKERFILE" || {
    echo "FAIL ${DOCKERFILE} does not copy packages/${package}; this script is stale" >&2
    exit 1
  }
done
while read -r copied; do
  [[ " ${PACKAGES[*]} " == *" ${copied} "* ]] || {
    echo "FAIL ${DOCKERFILE} copies packages/${copied}, which this script does not stage" >&2
    exit 1
  }
done < <(sed -n 's|^COPY packages/\([a-z_]*\) packages/[a-z_]*$|\1|p' "$DOCKERFILE")

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cp pyproject.toml uv.lock "$WORK/"
for package in "${PACKAGES[@]}"; do
  mkdir -p "$WORK/packages/${package}"
  cp -R "packages/${package}/." "$WORK/packages/${package}/"
done
for service in "${FULL_SERVICES[@]}"; do
  mkdir -p "$WORK/services/${service}"
  cp -R "services/${service}/." "$WORK/services/${service}/"
done
# Manifests only, because the workspace refuses to resolve with a member it
# cannot read — which is also why the Dockerfile copies them.
for service in "${MANIFEST_ONLY_SERVICES[@]}"; do
  mkdir -p "$WORK/services/${service}"
  cp "services/${service}/pyproject.toml" "$WORK/services/${service}/"
done
for tree in "${SOURCE_TREES[@]}"; do
  cp -R "$tree" "$WORK/${tree}"
done
mkdir -p "$WORK/demo"
cp -R demo/fixtures "$WORK/demo/fixtures"

echo "resolving the image's dependency set"
UV_PROJECT_ENVIRONMENT="$WORK/.venv" uv sync --frozen --package patchapi-agent-runner --no-dev \
  --directory "$WORK" >/dev/null

echo "importing the entry points from the staged tree"
# From `$WORK`, so a module that resolved only because the real checkout was on
# the path fails here as it would in the container.
cd "$WORK"
PYTHONPATH="$WORK" "$WORK/.venv/bin/python" - <<'PY'
import importlib

# What each container entry point pulls in transitively. `remediation.job`
# reaches the orchestrator, which reaches memory and tracing at module load.
for name in (
    "patchapi_agent_runner.serve",
    "patchapi_agent_runner.remediation.entrypoint",
    "patchapi_agent_runner.remediation.worker",
    "patchapi_agent_runner.remediation.job",
    "patchapi_agent_runner.telemetry",
    "agents.orchestrator",
):
    importlib.import_module(name)
    print(f"  ok {name}")

# Declared as dependencies rather than merely present on the path: an image can
# hold the source and still lack what the source imports.
from packages.memory.vertex import memory_bank_unavailable_reason
from packages.observability.export import cloud_trace_unavailable_reason

cloud = {"GCP_PROJECT": "patch-505223", "PATCHAPI_MEMORY_BANK_ENGINE": "0"}
for what, reason in (
    ("memory bank", memory_bank_unavailable_reason(cloud)),
    ("cloud trace", cloud_trace_unavailable_reason(cloud)),
):
    if reason is not None:
        raise SystemExit(f"FAIL {what} unavailable in a deployed environment: {reason}")
    print(f"  ok {what} reachable under the deployment's environment")
PY

cd "$ROOT"
echo "PASS the agent lane image contains what the agent lane imports"
