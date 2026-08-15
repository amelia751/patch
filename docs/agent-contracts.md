# Agent contracts

**Status:** Four reasoning agents and two Python stages (Policy, PR). The
Pydantic models under `packages/schemas/` are authoritative; the canonical
prose specification is
[`roadmap.md` §8](../roadmap.md#8-agent-responsibilities-and-contracts).

---

## Rules that apply to every agent

- **Google ADK only** for orchestration. No LangChain, LangGraph, LlamaIndex,
  CrewAI, AutoGen, or DSPy anywhere in the runtime path.
- **Gemini 3.5 Flash or newer** for reasoning, pinned via
  `PATCHAPI_REASONING_MODEL`. Never a third-party model.
- Every input and output is a **versioned schema**. Version strings live in
  configuration, not at call sites.
- Agents receive **capabilities, never raw credentials**.
- An agent that cannot complete its job honestly emits a failure or
  `HUMAN_REQUIRED`. It never invents a deprecation, model ID, test result, or
  sandbox outcome.
- The orchestrator decides the sequence. Agents supply judgment inside a step,
  not the choice of step — see
  [`roadmap.md` §9](../roadmap.md#9-deterministic-orchestration).

## 1. Change Intelligence Agent

| | |
|---|---|
| **In** | trusted-source snapshot: `source_url`, `retrieved_at`, `content_uri`, `content_sha256`, `provider` |
| **Out** | `ChangeManifest` |
| **Guardrail** | **may not access GitHub source code at all** |

Distinguishes announcement date from effective/shutdown date, extracts affected
identifiers and the recommended replacement, captures migration constraints, and
preserves source evidence. Provider text is data, never instruction.

`ChangeManifest` fields: `provider`, `change_id`, `change_type`, `severity`,
`announced_at`, `effective_at`, `affected_identifiers[]`,
`recommended_replacement`, `semantic_migration_required`, `source_urls[]`.

## 2. Impact Agent

| | |
|---|---|
| **In** | `ChangeManifest`, candidate repository inventory, API-usage index rows, permitted snippets, Memory Bank context |
| **Out** | `ImpactReport` |

Decides affected versus unaffected, which files and concrete usages, the
probable migration category, confidence, owning team, and testing requirements.

It must classify each hit as source/runtime, test, docs, example, configuration,
or dead code. **A docs-only hit is not a runtime hit** and must not be treated
as one.

`ImpactReport` fields: `repo`, `base_sha`, `affected`, `confidence`,
`findings[]` (`identifier`, `file`, `kind`), `migration_character`,
`required_checks[]`.

## 3. Policy (Python, not an LlmAgent)

| | |
|---|---|
| **In** | `ChangeManifest`, `ImpactReport`, deterministic enterprise policy, repository criticality, Memory Bank history |
| **Out** | `PolicyDecision` |

The orchestrator calls `packages.policy`. A model cannot loosen a deny.
Emits risk tier, allowed actions, forbidden actions, mandatory verification, and
whether human review is required: `risk`, `auto_patch`, `auto_pr`, `auto_merge`
(**always false**), `forbidden_globs[]`, `required_checks[]`, `reason`.

The enforcement hierarchy in [`security.md`](./security.md) is what actually
stops a bad action.

## 4. Patch Agent

| | |
|---|---|
| **In** | `ChangeManifest`, `ImpactReport`, policy decision, selected snippets or workspace, provider migration skill |
| **Out** | `PatchPlan` + unified diff |

Constraints: at most 2–3 attempts; **every attempt starts from the same pinned
base SHA**; no GitHub write credential inside the sandbox; no merge permission
anywhere; never self-approves.

`PatchPlan` fields: `run_id`, `base_sha`, `attempt`, `files_expected[]`,
`migration_summary`, `assumptions[]`, `verification_commands[]`.

## 5. Verification Agent

| | |
|---|---|
| **In** | original `ChangeManifest`, original affected snippets, the diff, build output, test output, live smoke-test output, artifacts, policy requirements |
| **Out** | `VerificationReport` — **holds veto power** |

Must be independent of patch generation. Answers six questions: did the patch
address the provider change; did it introduce unexplained scope; did required
tests pass; did the live replacement API call work; are prohibited files
untouched; is the evidence sufficient for a PR.

`VerificationReport` fields: `verdict`, `base_sha`, `patched_sha_or_diff_hash`,
`build`, `tests`, `live_api`, `policy`, `unexpected_files[]`, `evidence[]`.

Unavailable live verification is `INCONCLUSIVE`, never `PASS`.

## 6. PR publisher (Python, not an LlmAgent)

| | |
|---|---|
| **In** | a **verified** patch only (`VerificationReport.verdict == PASS`) |
| **Out** | branch, commit, pull request, evidence summary |

The orchestrator calls `github_tools` after PASS. It may not merge, bypass
checks, alter branch protection, or change CI configuration. It reaches GitHub
only through the narrow tool service, which owns the App credentials.

The PR body template — why, affected usage, migration, verification checklist,
risk, evidence, and an explicit automation-boundary statement — is in
[`roadmap.md` §8.6](../roadmap.md#8-agent-responsibilities-and-contracts).

## Failure semantics

Every agent inherits the fail-closed table in
[`roadmap.md` §22](../roadmap.md#22-failure-handling): provider source
unavailable means no invented migration; ambiguity means `HUMAN_REQUIRED`;
moved repository HEAD aborts PR creation; exhausted patch attempts mean
`FAILED`; failing tests mean no PR; unavailable live verification means
`INCONCLUSIVE`; verifier disagreement means no PR.

## Reality check

As of 2026-08-11 the ADK agent modules are being scaffolded by the setup batch
and no end-to-end run has produced a pull request. Gemini 3.5 Flash and
`gemini-3.1-flash-image` are confirmed reachable on the Vertex `global`
endpoint; the GitHub write path does not exist yet because the GitHub App is
deferred. See [`architecture.md`](./architecture.md) for the full status table.
