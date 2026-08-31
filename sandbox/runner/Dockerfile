# Sandbox runner image: the process that executes untrusted, generated code.
#
# Build with this directory as the context so nothing outside sandbox/runner can
# be baked into an image that untrusted code runs inside:
#
#   docker build -f sandbox/runner/Dockerfile -t patchapi-sandbox-runner sandbox/runner
#
# Posture notes (roadmap §13.2) that this file can carry, and the ones it
# cannot: non-root, no credentials, no build-time secrets, and a writable path
# limited to the sandbox root are set here. gVisor, dropped capabilities,
# resource limits, no service-account token, and default-deny networking are
# properties of the SandboxTemplate and NetworkPolicy under sandbox/gke/, not of
# the image.

# The pinned demo target is a pnpm/TypeScript CLI on Node 22, matching the
# toolchain recorded in demo/storygen/baseline.json.
FROM node:22.16.0-bookworm-slim

# git materialises the pinned base SHA; python3 hosts the runner itself, which
# is standard-library only and therefore installs no Python packages.
RUN apt-get update \
 && apt-get install --yes --no-install-recommends \
      ca-certificates \
      git \
      python3 \
 && rm -rf /var/lib/apt/lists/*

# Corepack caches per user. Preparing pnpm into a world-readable COREPACK_HOME
# is what stops the unprivileged runtime user from re-downloading pnpm on first
# use — which, under the default-deny egress policy, would simply hang.
ENV COREPACK_HOME=/opt/corepack

RUN mkdir -p "${COREPACK_HOME}" \
 && corepack enable \
 && corepack prepare pnpm@10.15.0 --activate \
 && chmod -R a+rX "${COREPACK_HOME}"

# Runs are rooted outside the code directory so a run can never be allocated
# inside the tree it is verifying.
ENV PATCHAPI_SANDBOX_ROOT=/sandbox \
    PYTHONPATH=/opt/patchapi \
    PYTHONDONTWRITEBYTECODE=1

RUN mkdir -p /sandbox /opt/patchapi/sandbox/runner \
 && chown -R node:node /sandbox /opt/patchapi

COPY --chown=node:node . /opt/patchapi/sandbox/runner/

# Unprivileged from here on. The image never receives a GitHub key, an admin
# token, or a control-plane credential (roadmap §13.4).
USER node
WORKDIR /opt/patchapi

ENTRYPOINT ["python3", "-m", "sandbox.runner.entrypoint"]
CMD ["--help"]
