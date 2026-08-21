# Build context is the repository root.
#   docker build -f services/repo_indexer/Dockerfile -t patchapi-indexer .
#
# Pub/Sub push hits this image on Cloud Run. Shards live on the container disk
# for the life of the instance; the durable inventory is Cloud SQL.
ARG ZOEKT_REF=v0.0.0-20260813151149-f18649803f5a
ARG AST_GREP_VERSION=0.45.1

FROM golang:1.25-bookworm AS zoekt
ARG ZOEKT_REF
ENV CGO_ENABLED=0
RUN go install "github.com/sourcegraph/zoekt/cmd/zoekt-index@${ZOEKT_REF}" \
 && go install "github.com/sourcegraph/zoekt/cmd/zoekt-git-index@${ZOEKT_REF}" \
 && go install "github.com/sourcegraph/zoekt/cmd/zoekt-webserver@${ZOEKT_REF}"

FROM rust:1.88-bookworm AS astgrep
ARG AST_GREP_VERSION
RUN cargo install ast-grep --locked --version "${AST_GREP_VERSION}" \
 && strip /usr/local/cargo/bin/ast-grep

FROM python:3.12-slim AS runtime

RUN apt-get update \
 && apt-get install --no-install-recommends -y git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=zoekt /go/bin/zoekt-index /usr/local/bin/zoekt-index
COPY --from=zoekt /go/bin/zoekt-git-index /usr/local/bin/zoekt-git-index
COPY --from=zoekt /go/bin/zoekt-webserver /usr/local/bin/zoekt-webserver
COPY --from=astgrep /usr/local/cargo/bin/ast-grep /usr/local/bin/ast-grep
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/schemas/pyproject.toml packages/schemas/
COPY packages/events/pyproject.toml packages/events/
COPY packages/auth/pyproject.toml packages/auth/
COPY packages/state/pyproject.toml packages/state/
COPY packages/repo_scan/pyproject.toml packages/repo_scan/
COPY services/control_api/pyproject.toml services/control_api/
COPY services/repo_indexer/pyproject.toml services/repo_indexer/

COPY packages/schemas packages/schemas
COPY packages/events packages/events
COPY packages/auth packages/auth
COPY packages/state packages/state
COPY packages/repo_scan packages/repo_scan
COPY services/control_api services/control_api
COPY services/repo_indexer services/repo_indexer

RUN uv sync --frozen --package patchapi-repo-indexer --no-dev

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PATCHAPI_INDEX_BACKEND=zoekt \
    PATCHAPI_ZOEKT_INDEX_DIR=/var/lib/patchapi/zoekt \
    PATCHAPI_INDEXER_WORKDIR=/var/lib/patchapi/checkouts

VOLUME ["/var/lib/patchapi"]

RUN useradd --system --uid 10001 --home /var/lib/patchapi indexer \
 && mkdir -p /var/lib/patchapi/zoekt /var/lib/patchapi/checkouts \
 && chown -R indexer:indexer /var/lib/patchapi
USER indexer

EXPOSE 8080

ENTRYPOINT ["patchapi-repo-indexer-serve"]
