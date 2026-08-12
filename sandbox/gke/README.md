# GKE Agent Sandbox

Status: live on `patchapi-dev-agentsandbox` (project `patch-505223`, zone
`us-central1-a`). Verified by `scripts/verify_sandbox_gke.sh`.

This directory is the isolation boundary PatchAPI puts between generated code
and everything else. Nothing here decides *what* to patch; it decides what a
patch is physically able to do while it is being proved.

## Files

| File | Purpose |
|---|---|
| `config.env` | Cluster, namespace, DNS, and image coordinates. The only place they are pinned. |
| `namespace.yaml` | `patchapi-sandbox-dev` with `restricted` Pod Security Admission. |
| `serviceaccount.yaml` | Sandbox identity with no bindings and no token. |
| `network-policy.yaml` | Namespace baseline: deny everything, allow DNS. |
| `phase-dependency-install.yaml` | Run-scoped egress for the install/build step. |
| `phase-live-verification.yaml` | Run-scoped egress for the replacement-model call. |
| `sandbox-template.yaml` | The pod shape every sandbox is created from. |
| `warm-pool.yaml` | One pre-provisioned sandbox for demo latency (roadmap §13.5). |
| `sandbox-claim.yaml` | One claim; the name is substituted per run. |

Cluster provisioning itself belongs to `infra/terraform/modules/gke_sandbox`.
Terraform never applies the manifests in this directory, so a broken template
cannot corrupt infrastructure state.

## Posture (roadmap §13.2)

Enforced by `sandbox-template.yaml` and asserted against the *running pod* by
the verifier — a manifest that claims a control is not evidence that the control
is in effect.

- `runtimeClassName: gvisor` on a `--sandbox=type=gvisor` node pool, so syscalls
  are handled in userspace rather than by the host kernel.
- `automountServiceAccountToken: false` on both the pod and the ServiceAccount,
  and the verifier `test -f`s the token path from inside the sandbox.
- `runAsNonRoot` / uid 1000, `allowPrivilegeEscalation: false`,
  `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`.
- `readOnlyRootFilesystem: true`; the only writable paths are size-capped
  `emptyDir` volumes at `/sandbox` and `/tmp`.
- CPU, memory, and ephemeral-storage limits on every container.
- No `hostNetwork`, `hostPID`, `hostIPC`, `privileged`, or `hostPath`.
- `GKE_METADATA` on the node pool blocks the legacy metadata endpoint, so a
  sandboxed process cannot read the node service account token.

## Network phases (roadmap §13.3)

A sandbox matches only `default-deny-all` and `allow-dns`: name resolution, and
nothing else. To open a phase, the orchestrator creates the phase policy —
scoped by name and by the sandbox's `claim-uid`, so it opens nothing for a
sandbox running beside it — and deletes it when the step ends.

| State | Allows |
|---|---|
| *(baseline)* | UDP/TCP 53 to the cluster and NodeLocal DNS resolvers |
| `phase-dependency-install` applied | TCP 443 to public addresses, excluding link-local and RFC 1918 |
| `phase-live-verification` applied | same L3/L4 surface, for the replacement-model call only |

**Phases are policy objects, not pod labels.** The Agent Sandbox controller
reconciles sandbox pod labels back to the SandboxTemplate, so a label written by
the orchestrator is reverted within seconds and a label-selected policy silently
stops matching. Creating and deleting the policy is the mechanism the controller
does not fight, and it is the one the verifier exercises.

**The template must opt out of managed network policy.** With
`spec.networkPolicyManagement` unset, the controller writes its own policy for
sandbox pods that allows egress to every public address. Kubernetes policies are
additive, so that would quietly override the default deny — observed on
GKE 1.35.6, and the reason `networkPolicyManagement: Unmanaged` is set.

A `NetworkPolicy` selects on addresses and ports, so it cannot express
"`generativelanguage.googleapis.com` and nothing else". What narrows the live
phase today is time and credentials: the policy is created immediately before
the call, the narrow Google credential is injected for that call alone, and both
are removed straight after. Hostname-level egress needs an authenticating egress
proxy or an FQDN policy — the follow-up recorded for the sandbox tree.

Excluding `169.254.0.0/16` and the RFC 1918 ranges is what makes the install
phase narrower than "internet access": generated code cannot reach the metadata
server, the cluster network, or another PatchAPI service.

## Credentials

The sandbox never receives the GitHub App private key, a GitHub admin or PR
write token, or a GCP control-plane credential (roadmap §13.4). Cluster
credentials are equally out of scope for the repository: the verifier writes a
`KUBECONFIG` into a run-scoped scratch directory under `tmp-patchapi/` and
deletes it on exit, and the registry token lives in a run-scoped
`docker --config` directory with the same lifetime.

## Running it

```bash
./scripts/verify_sandbox_gke.sh              # build, claim, exec, assert, destroy
./scripts/verify_sandbox_gke.sh --build-only # image only, no cloud calls
```

Evidence lands under `artifacts/sandbox-gke/<run-id>/`: build log, push log,
image digest, rendered manifests, `kubectl get`/`describe` output, exec output,
posture assertions, the three egress probes, and the post-delete listing.

The network assertions are the part worth reading. The verifier probes
`https://registry.npmjs.org/` from inside the sandbox three times — before the
phase policy exists, while it exists, and after it is deleted — and requires
deny, allow, deny. An allow is retried for a minute because Calico programs
policy asynchronously; a deny is never retried, because deny is the safe answer.

## Provisioning notes

The cluster was created with the Agent Sandbox addon enabled:

```jsonc
// container.googleapis.com/v1beta1 Cluster
"addonsConfig": { "agentSandboxConfig": { "enabled": true } }
```

Equivalent gcloud, once the local SDK is new enough to carry the flag
(540.0.0 does not):

```bash
gcloud beta container clusters create patchapi-dev-agentsandbox \
  --location us-central1-a --release-channel regular \
  --cluster-version 1.35.6-gke.1250000 \
  --workload-pool patch-505223.svc.id.goog \
  --enable-agent-sandbox
gcloud container node-pools create gvisor \
  --cluster patchapi-dev-agentsandbox --location us-central1-a \
  --sandbox type=gvisor --workload-metadata=GKE_METADATA
```

Agent Sandbox needs GKE 1.35.2-gke.1269000 or later
([install guide](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/how-install-agent-sandbox)).
The feature moves quickly; re-check the API group in `config.env` against the
docs before assuming a failure is ours.
