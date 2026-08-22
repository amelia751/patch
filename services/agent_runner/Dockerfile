# Build context is the repository root.
#   docker build -f services/agent_runner/Dockerfile -t patchapi-agents .
#
# No zoekt, no ast-grep, no git: this lane reads notices and calls a model. The
# index it needs has already been written to Cloud SQL by the indexer.
FROM python:3.12-slim AS runtime

RUN apt-get update \
 && apt-get install --no-install-recommends -y ca-certificates \
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
COPY agents/pyproject.toml agents/
COPY db/pyproject.toml db/

COPY packages/schemas packages/schemas
COPY packages/events packages/events
COPY packages/auth packages/auth
COPY packages/providers packages/providers
COPY packages/state packages/state
COPY packages/repo_scan packages/repo_scan
COPY packages/policy packages/policy
COPY services/agent_runner services/agent_runner

RUN uv sync --frozen --package patchapi-agent-runner --no-dev

# `patchapi-agents` declares `package = false`, so the fleet is imported from
# source rather than installed. `sandbox` is a namespace package the tool
# builders import at module load even though this lane grants no patch tools.
COPY agents agents
COPY sandbox sandbox
COPY demo/fixtures demo/fixtures

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
