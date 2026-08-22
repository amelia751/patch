# Build context is the repository root.
#   docker build -f services/github_tools/Dockerfile -t patchapi-github-tools .
#
# Deliberately the smallest image in the fleet. This service owns the GitHub App
# private key, so everything it does not need is something an attacker who
# reached it could not use: no database driver, no model client, no git, no
# sandbox. It signs a JWT, exchanges it for an installation token, and calls a
# fixed set of REST endpoints.
FROM python:3.12-slim AS runtime

RUN apt-get update \
 && apt-get install --no-install-recommends -y ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/github/pyproject.toml packages/github/
COPY services/github_tools/pyproject.toml services/github_tools/

COPY packages/github packages/github
COPY services/github_tools services/github_tools

RUN uv sync --frozen --package patchapi-github-tools --no-dev

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HOST=0.0.0.0

RUN useradd --system --uid 10001 --home /app ghtools
USER ghtools

EXPOSE 8080

ENTRYPOINT ["patchapi-github-tools"]
