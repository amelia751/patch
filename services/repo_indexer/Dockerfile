# Repository indexer — Layer A (Zoekt) and Layer B (ast-grep) in one image.
#
# The Go and Rust toolchains build the two binaries and are then discarded: the
# runtime stage carries the executables, git, and the Python service, and
# nothing that could compile new code inside a running container.
#
# Both dependencies are pinned (repo-indexer.md §4.1). Zoekt publishes no
# releases, so it is pinned to the module pseudo-version of a specific commit
# rather than to `main`, which would make two builds of this file produce
# different binaries.

ARG ZOEKT_REF=v0.0.0-20260813151149-f18649803f5a
ARG AST_GREP_VERSION=0.45.1

# Zoekt at this commit requires Go 1.25.9 or newer.
FROM golang:1.25-bookworm AS zoekt
ARG ZOEKT_REF
ENV CGO_ENABLED=0
# zoekt-webserver is included so the indexer can serve its own shards in a
# single-pod deployment; it binds to localhost only (see §5.2).
RUN go install "github.com/sourcegraph/zoekt/cmd/zoekt-index@${ZOEKT_REF}" \
 && go install "github.com/sourcegraph/zoekt/cmd/zoekt-git-index@${ZOEKT_REF}" \
 && go install "github.com/sourcegraph/zoekt/cmd/zoekt-webserver@${ZOEKT_REF}"

# ast-grep 0.45 requires rustc 1.88 or newer; the toolchain and the crate
# version move together.
FROM rust:1.88-bookworm AS astgrep
ARG AST_GREP_VERSION
RUN cargo install ast-grep --locked --version "${AST_GREP_VERSION}" \
 && strip /usr/local/cargo/bin/ast-grep

FROM python:3.12-slim AS runtime

# git is a runtime dependency, not a build one: zoekt-git-index reads refs from
# the mirror clones this service maintains.
RUN apt-get update \
 && apt-get install --no-install-recommends -y git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=zoekt /go/bin/zoekt-index /usr/local/bin/zoekt-index
COPY --from=zoekt /go/bin/zoekt-git-index /usr/local/bin/zoekt-git-index
COPY --from=zoekt /go/bin/zoekt-webserver /usr/local/bin/zoekt-webserver
COPY --from=astgrep /usr/local/cargo/bin/ast-grep /usr/local/bin/ast-grep

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# Workspace members the indexer imports. Copied before the source so a change to
# the service does not re-resolve the dependency graph.
COPY pyproject.toml uv.lock ./
COPY packages/schemas/pyproject.toml packages/schemas/
COPY packages/repo_scan/pyproject.toml packages/repo_scan/
COPY services/repo_indexer/pyproject.toml services/repo_indexer/

COPY packages/schemas packages/schemas
COPY packages/repo_scan packages/repo_scan
COPY services/repo_indexer services/repo_indexer

RUN uv sync --frozen --package patchapi-repo-indexer --no-dev

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PATCHAPI_INDEX_BACKEND=zoekt \
    PATCHAPI_ZOEKT_INDEX_DIR=/var/lib/patchapi/zoekt \
    PATCHAPI_INDEXER_WORKDIR=/var/lib/patchapi/checkouts

# Shards and mirror clones are the expensive state. Mount a persistent volume
# here: a cold start without one is a full rebuild of every index (§10).
VOLUME ["/var/lib/patchapi"]

RUN useradd --system --uid 10001 --home /var/lib/patchapi indexer \
 && mkdir -p /var/lib/patchapi/zoekt /var/lib/patchapi/checkouts \
 && chown -R indexer:indexer /var/lib/patchapi
USER indexer

ENTRYPOINT ["patchapi-repo-indexer"]
CMD ["--help"]
