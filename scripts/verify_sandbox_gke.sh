#!/usr/bin/env bash
# Dynamic verification for the GKE Agent Sandbox path (setup.md T-sandbox-gke).
#
# Two stages, and the second one is allowed to be skipped:
#
#   1. Build the sandbox runner image. Always required.
#   2. Against a live cluster: publish the image, apply the namespace, network
#      policies and SandboxTemplate, claim one sandbox, exec a command inside
#      it, prove the isolation posture from the running pod, then destroy the
#      claim and assert the sandbox object is gone.
#
# Stage 2 never reports PASS without kubectl output on disk. If the cluster is
# unreachable or Agent Sandbox is not installed, the script prints the exact
# error and exits non-zero — a sandbox we cannot verify is not a sandbox we can
# put generated code into.
#
# Usage:
#   ./scripts/verify_sandbox_gke.sh              # build + live cluster check
#   ./scripts/verify_sandbox_gke.sh --build-only # image only, no cloud calls
#
# Every coordinate comes from sandbox/gke/config.env and can be overridden in
# the environment.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GKE_DIR="${REPO_ROOT}/sandbox/gke"
RUNNER_DIR="${REPO_ROOT}/sandbox/runner"

# shellcheck source=../sandbox/gke/config.env
source "${GKE_DIR}/config.env"

BUILD_ONLY=0
[[ "${1:-}" == "--build-only" ]] && BUILD_ONLY=1
: "${PATCHAPI_SANDBOX_BUILD_ONLY:=0}"
[[ "${PATCHAPI_SANDBOX_BUILD_ONLY}" == "1" ]] && BUILD_ONLY=1

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
EVIDENCE_DIR="${REPO_ROOT}/artifacts/sandbox-gke/${RUN_ID}"
SCRATCH_DIR="${REPO_ROOT}/tmp-patchapi/sandbox-gke/${RUN_ID}"
mkdir -p "${EVIDENCE_DIR}" "${SCRATCH_DIR}"

# Cluster credentials are written into a run-scoped scratch file that is removed
# on exit, never into ~/.kube and never into a tracked path.
export KUBECONFIG="${SCRATCH_DIR}/kubeconfig"
DOCKER_CONFIG_DIR="${SCRATCH_DIR}/docker"

IMAGE_LOCAL="patchapi-sandbox-runner:${PATCHAPI_SANDBOX_IMAGE_TAG}"
IMAGE_REMOTE="${PATCHAPI_SANDBOX_IMAGE_REPO}/${PATCHAPI_SANDBOX_IMAGE_NAME}:${PATCHAPI_SANDBOX_IMAGE_TAG}"
CLAIM_NAME="patchapi-verify-${RUN_ID}"
CLAIM_NAME="$(printf '%s' "${CLAIM_NAME}" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-')"

log()  { printf '\n== %s\n' "$*"; }
fail() { printf '\nFAIL: %s\n' "$*" >&2; exit 1; }
skip() { printf '\nSKIP: %s\n' "$*"; exit 0; }

CLEANUP_CLAIM=0
PHASE_POLICY=""
cleanup() {
  local status=$?
  if [[ -n "${PHASE_POLICY}" ]]; then
    # A phase allowance must never survive the run that opened it, including a
    # run that died half way through.
    kubectl delete networkpolicy "${PHASE_POLICY}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" \
      --ignore-not-found >>"${EVIDENCE_DIR}/cleanup.txt" 2>&1 || true
  fi
  if [[ "${CLEANUP_CLAIM}" == "1" ]]; then
    log "destroying sandbox claim ${CLAIM_NAME}"
    kubectl delete sandboxclaim "${CLAIM_NAME}" \
      -n "${PATCHAPI_SANDBOX_NAMESPACE}" --ignore-not-found --wait=true --timeout=180s \
      >>"${EVIDENCE_DIR}/cleanup.txt" 2>&1 || true
    kubectl get sandboxes,pods -n "${PATCHAPI_SANDBOX_NAMESPACE}" \
      >>"${EVIDENCE_DIR}/cleanup.txt" 2>&1 || true
  fi
  # Credentials die with the run whether it passed or failed.
  rm -rf "${SCRATCH_DIR}"
  exit "${status}"
}
trap cleanup EXIT

need() { command -v "$1" >/dev/null 2>&1 || fail "$1 is not installed"; }

# ---------------------------------------------------------------------------
# Stage 1 — runner image
# ---------------------------------------------------------------------------
need docker
docker info >/dev/null 2>&1 || fail "docker daemon is not running"

log "building sandbox runner image (linux/amd64)"
# linux/amd64 is pinned because the gVisor node pool is x86; a silent arm64
# build would only fail once the pod was already scheduled.
docker build --platform linux/amd64 \
  -f "${RUNNER_DIR}/Dockerfile" \
  -t "${IMAGE_LOCAL}" \
  "${RUNNER_DIR}" 2>&1 | tee "${EVIDENCE_DIR}/docker-build.txt"

docker image inspect "${IMAGE_LOCAL}" >"${EVIDENCE_DIR}/image-inspect.json" \
  || fail "image ${IMAGE_LOCAL} missing after build"
echo "PASS: runner image built (${IMAGE_LOCAL})"

if [[ "${BUILD_ONLY}" == "1" ]]; then
  echo "SKIP: cluster stage disabled (--build-only)"
  echo "evidence: ${EVIDENCE_DIR}"
  exit 0
fi

# ---------------------------------------------------------------------------
# Stage 2 — live cluster
# ---------------------------------------------------------------------------
need gcloud
need kubectl

log "fetching credentials for ${PATCHAPI_GKE_CLUSTER} (${PATCHAPI_GKE_LOCATION})"
if ! gcloud container clusters get-credentials "${PATCHAPI_GKE_CLUSTER}" \
      --location "${PATCHAPI_GKE_LOCATION}" \
      --project "${PATCHAPI_GKE_PROJECT}" \
      >"${EVIDENCE_DIR}/get-credentials.txt" 2>&1; then
  cat "${EVIDENCE_DIR}/get-credentials.txt" >&2
  fail "cannot reach cluster ${PATCHAPI_GKE_CLUSTER}; see ${EVIDENCE_DIR}/get-credentials.txt"
fi
KUBE_CONTEXT="$(kubectl config current-context)"
echo "context: ${KUBE_CONTEXT}"

log "confirming Agent Sandbox CRDs are installed"
kubectl api-resources --api-group="${PATCHAPI_SANDBOX_TEMPLATE_API%%/*}" \
  >"${EVIDENCE_DIR}/api-resources.txt" 2>&1 || true
kubectl api-resources --api-group="${PATCHAPI_SANDBOX_API%%/*}" \
  >>"${EVIDENCE_DIR}/api-resources.txt" 2>&1 || true
grep -q 'sandboxtemplates' "${EVIDENCE_DIR}/api-resources.txt" \
  || fail "SandboxTemplate CRD absent — Agent Sandbox is not installed on ${PATCHAPI_GKE_CLUSTER}. $(cat "${EVIDENCE_DIR}/api-resources.txt")"
grep -q 'sandboxclaims' "${EVIDENCE_DIR}/api-resources.txt" \
  || fail "SandboxClaim CRD absent on ${PATCHAPI_GKE_CLUSTER}"

log "publishing runner image to ${IMAGE_REMOTE}"
# A run-scoped docker config keeps the registry token out of ~/.docker and out
# of the repository, and lets this script work on a host that has never run
# `gcloud auth configure-docker`.
mkdir -p "${DOCKER_CONFIG_DIR}"
python3 - "${DOCKER_CONFIG_DIR}/config.json" "${PATCHAPI_SANDBOX_IMAGE_REPO%%/*}" <<'PY'
import base64, json, subprocess, sys

path, registry = sys.argv[1], sys.argv[2]
token = subprocess.run(
    ["gcloud", "auth", "print-access-token"],
    capture_output=True, text=True, check=True,
).stdout.strip()
auth = base64.b64encode(f"oauth2accesstoken:{token}".encode()).decode()
json.dump({"auths": {registry: {"auth": auth}}}, open(path, "w"))
PY
chmod 600 "${DOCKER_CONFIG_DIR}/config.json"

docker tag "${IMAGE_LOCAL}" "${IMAGE_REMOTE}"
docker --config "${DOCKER_CONFIG_DIR}" push "${IMAGE_REMOTE}" \
  2>&1 | tee "${EVIDENCE_DIR}/docker-push.txt" \
  || fail "push to ${IMAGE_REMOTE} failed; see ${EVIDENCE_DIR}/docker-push.txt"

# The sandbox runs the exact bytes that were just pushed, not whatever the tag
# points at by the time the pod is scheduled. The digest is read from the push
# output rather than from `docker image inspect`, whose RepoDigests entry can
# still carry the local repository name.
PUSHED_DIGEST="$(awk '/^[a-z0-9._-]+: digest: sha256:/ {print $3}' "${EVIDENCE_DIR}/docker-push.txt" | tail -n 1)"
[[ -n "${PUSHED_DIGEST}" ]] || fail "no digest in push output; see ${EVIDENCE_DIR}/docker-push.txt"
IMAGE_DIGEST="${IMAGE_REMOTE%%:*}@${PUSHED_DIGEST}"
echo "image: ${IMAGE_DIGEST}" | tee "${EVIDENCE_DIR}/image-digest.txt"

log "applying namespace, service account and network policy"
sed -e "s|PATCHAPI_NODELOCAL_DNS_IP|${PATCHAPI_NODELOCAL_DNS_IP}|" \
    -e "s|PATCHAPI_CLUSTER_DNS_IP|${PATCHAPI_CLUSTER_DNS_IP}|" \
    "${GKE_DIR}/network-policy.yaml" >"${SCRATCH_DIR}/network-policy.rendered.yaml"
cp "${SCRATCH_DIR}/network-policy.rendered.yaml" "${EVIDENCE_DIR}/network-policy.rendered.yaml"
kubectl apply -f "${GKE_DIR}/namespace.yaml" \
  -f "${GKE_DIR}/serviceaccount.yaml" \
  -f "${SCRATCH_DIR}/network-policy.rendered.yaml" \
  2>&1 | tee "${EVIDENCE_DIR}/apply-base.txt"

kubectl get networkpolicy -n "${PATCHAPI_SANDBOX_NAMESPACE}" \
  >"${EVIDENCE_DIR}/networkpolicies.txt" 2>&1
grep -q 'default-deny-all' "${EVIDENCE_DIR}/networkpolicies.txt" \
  || fail "default-deny NetworkPolicy missing after apply"

log "applying SandboxTemplate"
sed "s|PATCHAPI_SANDBOX_IMAGE|${IMAGE_DIGEST}|" "${GKE_DIR}/sandbox-template.yaml" \
  >"${SCRATCH_DIR}/sandbox-template.rendered.yaml"
cp "${SCRATCH_DIR}/sandbox-template.rendered.yaml" "${EVIDENCE_DIR}/sandbox-template.rendered.yaml"
kubectl apply -f "${SCRATCH_DIR}/sandbox-template.rendered.yaml" \
  2>&1 | tee "${EVIDENCE_DIR}/apply-template.txt"

# Without the pool a claim schedules a pod from scratch, which measured 12s of a
# run that a warm claim serves in under a second. The pool is applied before the
# claim below so this script exercises the path a remediation actually takes.
log "applying SandboxWarmPool"
kubectl apply -f "${GKE_DIR}/warm-pool.yaml" \
  2>&1 | tee "${EVIDENCE_DIR}/apply-warm-pool.txt"
kubectl wait --for=jsonpath='{.status.replicas}'=1 \
  sandboxwarmpool/patchapi-node22-warm -n "${PATCHAPI_SANDBOX_NAMESPACE}" \
  --timeout=180s 2>&1 | tee "${EVIDENCE_DIR}/warm-pool-ready.txt" \
  || fail "SandboxWarmPool did not reach one ready replica"

log "claiming one sandbox: ${CLAIM_NAME}"
sed "s|PATCHAPI_SANDBOX_CLAIM|${CLAIM_NAME}|" "${GKE_DIR}/sandbox-claim.yaml" \
  >"${SCRATCH_DIR}/sandbox-claim.rendered.yaml"
CLEANUP_CLAIM=1
kubectl apply -f "${SCRATCH_DIR}/sandbox-claim.rendered.yaml" \
  2>&1 | tee "${EVIDENCE_DIR}/apply-claim.txt"

log "waiting for the sandbox pod to be ready"
# The pod is found through the label this template stamps on its pods rather
# than through a controller-owned label, whose name changes between Agent
# Sandbox releases.
POD=""
for _ in $(seq 1 60); do
  POD="$(kubectl get pods -n "${PATCHAPI_SANDBOX_NAMESPACE}" \
    -l app.kubernetes.io/name=patchapi-sandbox-runner \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  if [[ -n "${POD}" ]] && kubectl wait --for=condition=Ready "pod/${POD}" \
      -n "${PATCHAPI_SANDBOX_NAMESPACE}" --timeout=10s >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

kubectl get sandboxclaim,sandbox,pods -n "${PATCHAPI_SANDBOX_NAMESPACE}" -o wide \
  >"${EVIDENCE_DIR}/sandbox-objects.txt" 2>&1
[[ -n "${POD}" ]] || fail "no sandbox pod appeared for ${CLAIM_NAME}; $(cat "${EVIDENCE_DIR}/sandbox-objects.txt")"

kubectl describe pod "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" \
  >"${EVIDENCE_DIR}/pod-describe.txt" 2>&1
kubectl get pod "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" -o yaml \
  >"${EVIDENCE_DIR}/pod.yaml" 2>&1

log "exec smoke inside the sandbox"
kubectl exec "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" -- \
  sh -c 'echo patchapi-sandbox-ok; id -u; node --version; pnpm --version; python3 -c "import sandbox.runner.entrypoint as e; print(\"runner-import-ok\")"' \
  2>&1 | tee "${EVIDENCE_DIR}/exec-smoke.txt" \
  || fail "exec into ${POD} failed; see ${EVIDENCE_DIR}/exec-smoke.txt"

grep -q 'patchapi-sandbox-ok' "${EVIDENCE_DIR}/exec-smoke.txt" || fail "exec produced no marker"
# The pinned pnpm must resolve from the image. If it does not, corepack reaches
# for the registry and the whole toolchain becomes network-dependent.
grep -q '^10\.15\.0$' "${EVIDENCE_DIR}/exec-smoke.txt" || fail "pnpm 10.15.0 not resolved from the image"
grep -q 'runner-import-ok'    "${EVIDENCE_DIR}/exec-smoke.txt" || fail "runner package not importable inside the sandbox"
if grep -qx '0' "${EVIDENCE_DIR}/exec-smoke.txt"; then
  fail "sandbox process is running as root (uid 0)"
fi

log "asserting isolation posture from the running pod"
POSTURE_FAILS=0
assert_pod() {
  local jsonpath="$1" expected="$2" what="$3"
  local actual
  actual="$(kubectl get pod "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" -o jsonpath="${jsonpath}" 2>/dev/null || true)"
  if [[ "${actual}" == "${expected}" ]]; then
    printf 'ok    %-34s %s\n' "${what}" "${actual}" | tee -a "${EVIDENCE_DIR}/posture.txt"
  else
    printf 'FAIL  %-34s got=%q want=%q\n' "${what}" "${actual}" "${expected}" | tee -a "${EVIDENCE_DIR}/posture.txt"
    POSTURE_FAILS=$((POSTURE_FAILS + 1))
  fi
}
assert_pod '{.spec.runtimeClassName}' 'gvisor' 'gVisor runtime'
assert_pod '{.spec.automountServiceAccountToken}' 'false' 'no service-account token'
assert_pod '{.spec.securityContext.runAsNonRoot}' 'true' 'non-root'
assert_pod '{.spec.containers[0].securityContext.allowPrivilegeEscalation}' 'false' 'no privilege escalation'
assert_pod '{.spec.containers[0].securityContext.capabilities.drop[0]}' 'ALL' 'capabilities dropped'
assert_pod '{.spec.hostNetwork}' '' 'no host network'
[[ -n "$(kubectl get pod "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" -o jsonpath='{.spec.containers[0].resources.limits.memory}')" ]] \
  || { echo "FAIL  memory limit unset" | tee -a "${EVIDENCE_DIR}/posture.txt"; POSTURE_FAILS=$((POSTURE_FAILS + 1)); }

# A mounted token would be the single most damaging leak into generated code,
# so it is checked from inside the sandbox and not only from the pod spec.
if kubectl exec "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" -- \
     test -f /var/run/secrets/kubernetes.io/serviceaccount/token >/dev/null 2>&1; then
  echo "FAIL  service-account token is mounted inside the sandbox" | tee -a "${EVIDENCE_DIR}/posture.txt"
  POSTURE_FAILS=$((POSTURE_FAILS + 1))
else
  echo "ok    no token file inside the sandbox" | tee -a "${EVIDENCE_DIR}/posture.txt"
fi

log "asserting network isolation from inside the sandbox"
# The controller writes a permissive NetworkPolicy of its own unless the
# template opts out, so the default deny is proved by traffic, not by manifest.
EGRESS_PROBE='import urllib.request; urllib.request.urlopen("https://registry.npmjs.org/", timeout=8); print("egress-reachable")'

probe_egress() {  # 0 when the sandbox reached the registry
  kubectl exec "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" -- python3 -c "${EGRESS_PROBE}" \
    >>"$1" 2>&1
}

if probe_egress "${EVIDENCE_DIR}/egress-denied-before.txt"; then
  echo "FAIL  sandbox reached the public internet with no phase open" | tee -a "${EVIDENCE_DIR}/posture.txt"
  POSTURE_FAILS=$((POSTURE_FAILS + 1))
else
  echo "ok    egress denied before the install phase" | tee -a "${EVIDENCE_DIR}/posture.txt"
fi

CLAIM_UID="$(kubectl get pod "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" \
  -o jsonpath='{.metadata.labels.agents\.x-k8s\.io/claim-uid}')"
[[ -n "${CLAIM_UID}" ]] || fail "sandbox pod carries no claim-uid label to scope a phase policy to"
PHASE_POLICY="phase-install-${CLAIM_NAME}"

sed -e "s|PATCHAPI_PHASE_POLICY_NAME|${PHASE_POLICY}|" \
    -e "s|PATCHAPI_SANDBOX_CLAIM_UID|${CLAIM_UID}|" \
    "${GKE_DIR}/phase-dependency-install.yaml" >"${SCRATCH_DIR}/phase-install.rendered.yaml"
cp "${SCRATCH_DIR}/phase-install.rendered.yaml" "${EVIDENCE_DIR}/phase-install.rendered.yaml"
kubectl apply -f "${SCRATCH_DIR}/phase-install.rendered.yaml" \
  2>&1 | tee "${EVIDENCE_DIR}/apply-phase.txt"

# Calico programs a new policy asynchronously, so an allow is retried before it
# is called a failure. A deny is never retried: it is the safe answer.
PHASE_OPEN=1
for _ in $(seq 1 12); do
  if probe_egress "${EVIDENCE_DIR}/egress-install-phase.txt"; then
    PHASE_OPEN=0
    break
  fi
  sleep 5
done
if [[ "${PHASE_OPEN}" -eq 0 ]]; then
  echo "ok    egress allowed while the install phase is open" | tee -a "${EVIDENCE_DIR}/posture.txt"
else
  echo "FAIL  install phase cannot reach the package registry" | tee -a "${EVIDENCE_DIR}/posture.txt"
  POSTURE_FAILS=$((POSTURE_FAILS + 1))
fi

# Closing the phase must close the network with it — an allowance that outlives
# its step is the same as no allowance at all.
kubectl delete networkpolicy "${PHASE_POLICY}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" \
  --ignore-not-found >>"${EVIDENCE_DIR}/apply-phase.txt" 2>&1
PHASE_CLOSED=1
for _ in $(seq 1 12); do
  if ! probe_egress "${EVIDENCE_DIR}/egress-denied-after.txt"; then
    PHASE_CLOSED=0
    break
  fi
  sleep 5
done
if [[ "${PHASE_CLOSED}" -eq 0 ]]; then
  echo "ok    egress denied again once the phase is closed" | tee -a "${EVIDENCE_DIR}/posture.txt"
else
  echo "FAIL  egress still open after the phase policy was deleted" | tee -a "${EVIDENCE_DIR}/posture.txt"
  POSTURE_FAILS=$((POSTURE_FAILS + 1))
fi

# The metadata server is the path from a sandboxed process to a node
# credential; it must stay unreachable in every phase.
METADATA_PROBE='import urllib.request; urllib.request.urlopen("http://169.254.169.254/computeMetadata/v1/instance/", timeout=8); print("metadata-reachable")'
if kubectl exec "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" -- python3 -c "${METADATA_PROBE}" \
     >>"${EVIDENCE_DIR}/egress-denied.txt" 2>&1; then
  echo "FAIL  sandbox reached the GCE metadata server" | tee -a "${EVIDENCE_DIR}/posture.txt"
  POSTURE_FAILS=$((POSTURE_FAILS + 1))
else
  echo "ok    metadata server unreachable" | tee -a "${EVIDENCE_DIR}/posture.txt"
fi

[[ "${POSTURE_FAILS}" -eq 0 ]] || fail "${POSTURE_FAILS} posture assertion(s) failed; see ${EVIDENCE_DIR}/posture.txt"

log "destroying the sandbox"
kubectl delete -f "${SCRATCH_DIR}/sandbox-claim.rendered.yaml" --wait=true --timeout=180s \
  2>&1 | tee "${EVIDENCE_DIR}/delete-claim.txt"
CLEANUP_CLAIM=0

for _ in $(seq 1 36); do
  if ! kubectl get pod "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
kubectl get sandboxclaims,sandboxes,pods -n "${PATCHAPI_SANDBOX_NAMESPACE}" \
  >"${EVIDENCE_DIR}/after-delete.txt" 2>&1
if kubectl get pod "${POD}" -n "${PATCHAPI_SANDBOX_NAMESPACE}" >/dev/null 2>&1; then
  fail "sandbox pod ${POD} still exists after delete; see ${EVIDENCE_DIR}/after-delete.txt"
fi

echo
echo "PASS: sandbox claimed, exec verified, posture asserted, sandbox destroyed"
echo "cluster:  ${PATCHAPI_GKE_CLUSTER} (${PATCHAPI_GKE_LOCATION})"
echo "context:  ${KUBE_CONTEXT}"
echo "image:    ${IMAGE_DIGEST}"
echo "evidence: ${EVIDENCE_DIR}"
