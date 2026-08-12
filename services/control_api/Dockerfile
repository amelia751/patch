# Build context is the repository root, because this service installs the
# workspace-local contracts package alongside itself:
#   docker build -f services/control_api/Dockerfile -t patchapi-control-api .
FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Contracts first: they change less often than the service that carries them.
COPY packages/schemas/ ./packages/schemas/
COPY services/control_api/ ./services/control_api/

# Installed into a relocatable prefix so the runtime stage carries the
# libraries without the build tooling that produced them.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install ./packages/schemas ./services/control_api


FROM python:3.12-slim AS runtime

# No build toolchain, no compiler, no git: the control plane routes HTTP and
# must not be able to build or run anything a customer repository supplied.
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY --from=build /opt/venv /opt/venv

# Unprivileged and without a login shell. Nothing in this image writes to disk
# at runtime.
RUN useradd --system --create-home --shell /usr/sbin/nologin patchapi
USER patchapi
WORKDIR /home/patchapi

EXPOSE 8080

# The console script reads PORT, which is what Cloud Run injects.
CMD ["patchapi-control-api"]
