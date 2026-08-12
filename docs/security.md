# Security model

**Status:** Scaffold (2026-08-11) — states the controls PatchAPI is built
around and marks which ones are enforced in code today versus designed. Threat
enumeration lives in [`threat-model.md`](./threat-model.md). Authoritative
sources: [`roadmap.md` §14](../roadmap.md#14-github-security-model),
[`roadmap.md` §13](../roadmap.md#13-gke-agent-sandbox-design), and
[`CLAUDE.md`](../CLAUDE.md).

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

1. GitHub App permissions — the capability simply does not exist
2. Agent Identity / IAM
3. Agent Gateway allow policies
4. deterministic path and action allowlists in the policy package
5. sandbox network restrictions (default deny)
6. Semantic Governance and Model Armor as an additional dynamic layer

Layers 1–5 are deterministic. Layer 6 is probabilistic and is defense in depth
only; Google's own documentation notes that LLM-based policy verdicts are
probabilistic, so no security claim in this project rests on layer 6 alone.

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
.github/workflows/**
infra/**
terraform/**
.env*
```

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

## Enforced today versus designed

| Control | Today |
|---|---|
| No-merge boundary | designed; enforced by construction once the GitHub tool service ships — **the GitHub App is deferred, so there is no write path at all right now** |
| Deterministic forbidden-path policy | landing with the policy package in the setup batch |
| Independent verification | designed; part of the Phase 1 vertical slice |
| Isolated execution | **local temp workspace only.** GKE Agent Sandbox is not yet provisioned, so gVisor and network-policy claims above are design, not deployment |
| Model Armor / Semantic Governance | API access confirmed on the `global` location; **zero templates configured** |
| Secrets kept out of git | enforced now via `.gitignore` and `.secrets/` |

Do not cite this document as evidence that a control is live. Cite the
verification script that proves it.
