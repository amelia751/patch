# Build context is the repository root: the wired control plane installs
# contracts, auth, and the Postgres composition root alongside this service.
#   docker build -f services/control_api/Dockerfile -t patchapi-api .
FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY packages/schemas/ ./packages/schemas/
COPY packages/auth/ ./packages/auth/
COPY packages/state/ ./packages/state/
COPY services/control_api/ ./services/control_api/

# Installed into a relocatable prefix so the runtime stage carries the
# libraries without the build tooling that produced them. Order matches
# the workspace dependency direction: schemas → auth / control-api → state.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install \
        ./packages/schemas \
        ./packages/auth \
        ./services/control_api \
        ./packages/state


FROM python:3.12-slim AS runtime

# No build toolchain, no compiler, no git: the control plane routes HTTP and
# must not be able to build or run anything a customer repository supplied.
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HOST=0.0.0.0

COPY --from=build /opt/venv /opt/venv

# Unprivileged and without a login shell. Nothing in this image writes to disk
# at runtime. Secrets arrive as env / Secret Manager, never as files in the image.
RUN useradd --system --create-home --shell /usr/sbin/nologin patchapi
USER patchapi
WORKDIR /home/patchapi

EXPOSE 8080

# Wired composition root: Postgres + auth + the control plane. The unwired
# `patchapi-control-api` entry point is still on PATH for local probes.
CMD ["patchapi-serve"]
