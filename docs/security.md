# Security model

**Status:** Revised 2026-08-30 — states the controls PatchAPI is built around
and marks which ones are enforced in code today versus designed. Threat
enumeration lives in [`threat-model.md`](./threat-model.md). Authoritative
sources: [`roadmap.md` §14](../roadmap.md#14-github-security-model),
[`roadmap.md` §13](../roadmap.md#13-gke-agent-sandbox-design), and
[`CLAUDE.md`](../CLAUDE.md). The roadmap plans Agent Identity and Agent Gateway
as security controls; they are not available to this deployment and are not
part of the hierarchy below — see
[`architecture.md`](./architecture.md#google-platform-integration).

---

## The five load-bearing rules

1. **Stop at the pull request.** No merge, no deploy, no branch-protection
   edits, no secret rotation, no CODEOWNERS or CI bypass. Existing enterprise
   controls stay authoritative.
2. **External providers are untrusted input.** Release notes, changelogs,
   OpenAPI diffs, migration guides, and provider-authored agents are *data*.
   Only PatchAPI's internal agents decide what a change means for customer code.
3. **Generated code runs only in isolation.** Never in a developer checkout,
   never in the control plane.
4. **Verification is independent.** The model that wrote the patch does not
   grade it. No PR without an independent pass.
5. **Fail closed.** Missing evidence, ambiguous migration, policy denial, failed
   tests, unavailable live check, or verifier disagreement all mean *no PR*.

## Enforcement hierarchy

Hard controls must not depend solely on an LLM
([`roadmap.md` §8.3](../roadmap.md#8-agent-responsibilities-and-contracts)).
Ordered strongest to weakest:

1. **GitHub App permissions** — the capability simply does not exist
2. **The tool service's own surface** — `services/github_tools/` implements no
   merge, administration, secret, or branch-protection operation, so there is
   nothing to authorize
3. **Cloud Run IAM plus Google-signed ID tokens** — the tool service is private
   and answers only named service accounts
4. **Deterministic path, command, and injection rules** in `packages/policy/` —
   forbidden globs, the command allowlist, and `contains_injection`
5. **Sandbox network restrictions** (default deny)
6. **Model Armor** as an additional dynamic layer

Layers 1–5 are deterministic. Layer 6 is probabilistic *and fails open*, which
is a stronger reason to distrust it than probabilism alone: Google documents
that Model Armor's Vertex integration lets a prompt proceed unscreened when the
service errors. No security claim in this project rests on layer 6, and
`packages/policy/armor.py` composes the two gates so that Model Armor can only
add a refusal, never withdraw one.

Layers 2 and 3 are what PatchAPI has instead of Agent Identity and Agent
Gateway. They are weaker in one specific way and the difference is worth
stating: there is no SPIFFE attestation of which agent is calling the tool
service, and no network-layer refusal of a tool by name. The caller's agent name
travels in an `X-PatchAPI-Agent` header, and a header is a scoping hint, not an
attestation. The guarantee that PatchAPI cannot merge does not depend on it —
that comes from layers 1 and 2, where the operation does not exist.

## Credential boundary

No agent ever holds a raw credential.

```text
Sandbox  ──verified diff──▶  Verification Agent  ──▶  PR Agent
                                                        │
                                          narrow GitHub tool service
                                          (sole holder of the App key)
                                                        │
                                        installation token → branch/commit/PR
```

The sandbox never pushes to GitHub. It must never receive the GitHub App
private key, any GitHub admin or PR-write token, or GCP control-plane
credentials. For the final live replacement-API smoke test, a narrow Google
credential is provided for that step only and removed immediately afterward.

Locally, credentials live in `.secrets/` (gitignored) and are referenced through
environment variables named in [`.env.example`](../.env.example). No secret ever
enters the repository, a prompt, an agent trace, a log line, or these docs.

## GitHub capability surface

The tool service exposes an allowlist and nothing else
([`roadmap.md` §7.3](../roadmap.md#7-deployment-units)):

| Reads | Writes | Explicitly absent |
|---|---|---|
| `get_repository_metadata` | `create_patch_branch` | `merge_pull_request` |
| `get_file` | `commit_verified_patch` | `change_branch_protection` |
| `list_tree` | `open_pull_request` | `modify_actions_secrets` |
| `get_commit` | `add_pr_comment` | `modify_repository_admin_settings` |
| `get_pull_request` | | `delete_repository` |
| `get_checks` | | |

App permissions are scoped to match: Metadata read; Contents read+write; Pull
requests read+write; Checks read; Administration, Secrets, and Deployments
**none**; Workflows write avoided. A forbidden capability is a structured
rejection, not a silent no-op.

## Sandbox posture

Per [`roadmap.md` §13.2](../roadmap.md#13-gke-agent-sandbox-design): gVisor
runtime, non-root, no automatically mounted service-account token, dropped Linux
capabilities, CPU and memory limits, no privileged containers, no host
networking, no HostPath.

Network policy starts default-deny and opens only per phase — package registries
and the repository read path during dependency install; the single Google API
endpoint needed for image generation during live verification. Generated code
never gets arbitrary internet access.

## Path policy

The Patch Agent's mutation boundary is application code. Deterministic
forbidden globs — enforced in the policy package before any diff is applied, not
by asking a model nicely:

```text
.github/workflows/**      CI definitions decide which checks grade a patch
**/CODEOWNERS             review ownership is the human control PatchAPI stops at
.secrets/**, **/*.pem     credential material is never read, written, or rotated
infra/**, terraform/**    infrastructure changes the blast radius of a deploy
**/iam/**, **/rbac/**     an API migration never needs more privilege
packages/policy/**        PatchAPI does not edit the rules that constrain PatchAPI
```

One pattern per rule above; `FORBIDDEN_PATH_RULES` in
`packages/policy/config.py` is the complete list and `POLICY_VERSION` is
recorded on every evaluation so an old decision can be explained by the rules
that were in force when it was made. A second, weaker table escalates lockfiles,
dependency manifests, and container definitions to `HUMAN_REQUIRED` rather than
blocking, because refusing those outright would make ordinary
dependency-bearing migrations impossible.

An instruction inside provider text or repository content that asks for an edit
outside this boundary is refused by the path check, which is exactly the
scripted security demonstration in
[`roadmap.md` §16](../roadmap.md#16-security-demo).

## Audit

Every meaningful action emits an audit event, whether or not a model was
involved: run ID, timestamp, actor type and ID, action, resource, base SHA,
policy verdict, trace ID. The audit trail must be able to answer which external
change triggered a run, which source document version was used, which SHA was
analyzed, which agent decided what, which policy allowed the edit, which files
changed, which commands ran, what the tests returned, which endpoints were
contacted, which verifier approved, and which identity opened the PR
([`roadmap.md` §18](../roadmap.md#18-observability-and-audit-design)). Storage
shape: [`data-model.md`](./data-model.md).

## Traces leave the trust boundary

Spans are exported over OTLP to Google's Telemetry API and read by people who
are not reviewing this repository, so what may travel on one is restricted in
two independent places.

**PatchAPI's own spans.** `StageSpan.set` in `agents/observe.py` accepts only
the keys pinned in `packages/observability/config.py`, and only values shaped
like an identifier — no whitespace, one line, bounded length. Every untrusted
document this product handles is prose, and prose does not survive that pattern.
Span events carry a name and no payload.

**ADK's spans.** `google-adk` 2.1.0 writes the whole prompt and the whole
response onto its `call_llm` spans as JSON, and it does so *by default*:
`ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS` defaults to `true`. A PatchAPI prompt
carries provider release notes and the customer's own source, so leaving that
default would export untrusted third-party text and private code to a trace
backend the moment tracing was switched on — the exact opposite of what the
intake gate exists for.

`services/agent_runner/src/patchapi_agent_runner/telemetry.py` sets it to
`false` in code, before the tracer provider exists so no span can be built under
the default. It is set in the process rather than in the deployment on purpose:
the safe posture is then a property of the code and not of a flag someone can
forget. `setdefault`, so an operator debugging one run can still opt in
deliberately, and the process logs a warning when they have.
`services/agent_runner/tests/test_telemetry.py` is the regression test.

## Enforced today versus designed

| Control | Today |
|---|---|
| No-merge boundary | **enforced by construction.** The GitHub App is installed and the write path is live; the tool service implements no merge, admin, secret, or branch-protection operation |
| Deterministic forbidden-path policy | **enforced** in `packages/policy/` (`FORBIDDEN_PATH_RULES`, `POLICY_VERSION` recorded on every evaluation) |
| Deterministic injection gate on untrusted text | **enforced** in `packages/policy/injection.py`, and applied to recalled Memory Bank text as well as provider text |
| Independent verification | **enforced.** A separate Verification Agent must pass before a PR, and it is never shown institutional memory |
| Isolated execution | **partial.** The GKE cluster exists and `./scripts/verify_sandbox_gke.sh` claims and destroys a live sandbox, but the backend is per-run. A run on the local temp workspace is not sandboxed execution and the gVisor and network-policy claims above do not describe it |
| Model Armor | template and project floor settings configured; the intake `sanitizeUserPrompt` call is **opt-in via `PATCHAPI_MODEL_ARMOR_ENABLED`, which the deploy workflow does not set**, so a deployed run screens with the deterministic gate alone and reports it. Verified live by `PATCHAPI_MODEL_ARMOR_LIVE=1 ./scripts/verify_policy_model_armor.sh` |
| Semantic Governance | not wired. `RuleTier.SEMANTIC_GOVERNANCE` is the tier Model Armor findings carry, not a separate Google service |
| Prompt and model output kept off exported spans | **enforced** in the agent-lane entry point; see [Traces leave the trust boundary](#traces-leave-the-trust-boundary) |
| Per-agent SPIFFE identity / network-layer tool denial | **not available.** Agent Identity and Agent Gateway do not support Cloud Run deployments |
| Secrets kept out of git | enforced now via `.gitignore` and `.secrets/` |

Do not cite this document as evidence that a control is live. Cite the
verification script that proves it.
