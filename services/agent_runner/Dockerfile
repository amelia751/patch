# Build context is the repository root.
#   docker build -f services/agent_runner/Dockerfile -t patchapi-agents .
#
# One image, two entry points. `patchapi-agent-runner-serve` reads notices and
# calls a model; `patchapi-remediate` runs one remediation as a Cloud Run job.
# They share every line of the agent fleet, so a second image would only be a
# second thing to keep in step.
#
# The job adds two tools the serving lane never uses. `git` reads the customer
# repository at the pinned commit — into a scratch directory on this side, never
# into the sandbox, so no credential travels with the tree. `kubectl` claims the
# GKE sandbox. The Google Cloud SDK is deliberately absent: cluster credentials
# are written from Application Default Credentials by `sandbox.gke.kubeconfig`,
# which costs one small file instead of several hundred megabytes.
#
# No zoekt and no ast-grep: the index this lane reads was written to Cloud SQL
# by the indexer.
FROM python:3.12-slim AS runtime

ARG KUBECTL_VERSION=v1.32.1

RUN apt-get update \
 && apt-get install --no-install-recommends -y ca-certificates git curl \
 && curl -fsSLo /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
 && chmod 0755 /usr/local/bin/kubectl \
 && kubectl version --client=true --output=yaml >/dev/null \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/schemas/pyproject.toml packages/schemas/
COPY packages/events/pyproject.toml packages/events/
COPY packages/auth/pyproject.toml packages/auth/
COPY packages/providers/pyproject.toml packages/providers/
COPY packages/state/pyproject.toml packages/state/
COPY packages/repo_scan/pyproject.toml packages/repo_scan/
COPY packages/policy/pyproject.toml packages/policy/
COPY services/control_api/pyproject.toml services/control_api/
COPY services/repo_indexer/pyproject.toml services/repo_indexer/
COPY services/agent_runner/pyproject.toml services/agent_runner/

COPY packages/schemas packages/schemas
COPY packages/events packages/events
COPY packages/auth packages/auth
COPY packages/providers packages/providers
COPY packages/state packages/state
COPY packages/repo_scan packages/repo_scan
COPY packages/policy packages/policy
# patchapi-state depends on patchapi-control-api, so the member has to be
# resolvable in full rather than by its manifest alone.
COPY services/control_api services/control_api
COPY services/agent_runner services/agent_runner

RUN uv sync --frozen --package patchapi-agent-runner --no-dev

# `patchapi-agents` declares `package = false`, so the fleet is imported from
# source rather than installed. `sandbox` is a namespace package the tool
# builders import at module load even though this lane grants no patch tools.
COPY agents agents
COPY sandbox sandbox
COPY demo/fixtures demo/fixtures
# `load_migration_skill` reads these from PATCHAPI_REPO_ROOT. Without them the
# patch stage has the provider's notice and none of the capability differences
# that make a migration more than a string replacement.
COPY skills skills

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PATCHAPI_REPO_ROOT=/app \
    PATCHAPI_FEED_DIR=/app/demo/fixtures

RUN useradd --system --uid 10001 --home /app agents
USER agents

EXPOSE 8080

ENTRYPOINT ["patchapi-agent-runner-serve"]
