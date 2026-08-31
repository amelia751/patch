# PatchAPI — project conventions

Dependabot for APIs. When an external API changes, PatchAPI finds the affected
code, generates and verifies a migration in an isolated environment, and opens
an evidence-backed pull request for normal human review.

Built for *All Things Agentic Hackathon* — Fortified Enterprise Fleet track.

- **Execution plan:** `roadmap.md` — the authoritative source for architecture,
  agent contracts, demo target, security model, and phased build order. Read it
  before changing architecture.

## Hard constraints

These come from the competition rules and the product specification. Breaking one
can disqualify the submission or break the enterprise trust model.

1. **Google ADK only** for agent orchestration at runtime. No LangChain,
   LangGraph, LlamaIndex, CrewAI, AutoGen, or DSPy in the runtime path.
2. **Gemini 3.5 Flash or newer** for PatchAPI agent reasoning. Default hackathon
   configuration is Gemini 3.5 Flash. No third-party models in the product's
   runtime path.
3. **Stop at the pull request.** PatchAPI never merges, never deploys, never
   edits branch protection, never rotates secrets, and never bypasses CODEOWNERS
   or CI. Existing enterprise controls remain authoritative.
4. **External providers are untrusted.** Release notes, changelogs, OpenAPI
   diffs, migration guides, and provider-authored agents are untrusted input.
   Only PatchAPI's internal enterprise agents decide what a change means for
   customer code. Provider agents never receive unrestricted source access.
5. **Generated code runs only in isolation.** Patches execute inside a GKE Agent
   Sandbox (or a local temp workspace during early phases). Never apply
   unverified agent output to a developer's primary checkout as "done".
6. **Independent verification.** The patch-producing model does not grade its
   own work. A separate Verification Agent must pass before a PR is opened.
7. **Postgres is authoritative workflow state.** Memory Bank holds institutional
   context across weeks; it is not the source of truth for run status,
   idempotency, or audit. Deterministic state lives in Cloud SQL / local
   Postgres (SQLite only for early local vertical-slice work).
8. **Narrow GitHub capabilities.** Agents call a GitHub tool service that owns
   the GitHub App credentials. Agents receive capabilities, never raw tokens.
   The tool surface has no merge, no admin, no secret, no branch-protection APIs.
9. **No secrets in the repository.** Credentials live in `.secrets/` (gitignored)
   and are referenced through environment variables.
10. **Do not invent migrations.** If the provider source is unavailable or the
    change is ambiguous, mark `HUMAN_REQUIRED` / fail closed. Never fabricate a
    deprecation, a model ID, a test result, or a sandbox outcome.
11. **Pin the demo target.** The demo repository is `amelia751/storygen`.
    Exact SHAs and fixtures live under `demo/`.

## Layout

```
apps/web/                Next.js + TypeScript control UI
services/control_api/    FastAPI control plane
services/github_tools/   Narrow GitHub App capability adapter
services/repo_indexer/   API usage inventory indexer
agents/                  Google ADK agents (orchestrator + six specialists)
packages/                Shared schemas, providers, policy, events, memory, OTel
skills/                  Provider migration skills (Skill Registry shape)
sandbox/                 Sandbox runner image + GKE templates
db/                      Migrations and seeds
infra/terraform/         GCP provisioning
demo/                    Provider notice fixtures and demo artifacts
docs/                    Architecture, data model, operations
tests/                   Unit, integration, agent eval, adversarial
```

Where `roadmap.md` §6 and this block disagree on a path, follow this block only
after updating the roadmap in the same change.

## Conventions

- Python 3.12 with type hints on public functions; `ruff` for lint and format;
  `uv` for package management.
- TypeScript strict mode; `npm` for the dashboard (`apps/web`).
- Schemas are Pydantic; every agent I/O contract is versioned.
- Model IDs, prompt versions, and schema versions live in configuration and are
  pinned, never inlined at a call site.
- Comments explain constraints and intent. They never narrate what the code does.
- Tests accompany the code they cover, and the command that runs them is recorded
  in the pull request or worker report.
- Commit messages state what changed in the codebase and why, in the imperative
  mood. They never name the tooling that produced the change — no models, no
  agents, no fleet tasks, roles or attempt counts, and no `Co-authored-by` or
  `Generated with` trailers. One commit per concern.

## Working with the agent fleet

Local-only tooling lives in `.fleet/` (gitignored). It dispatches headless Claude
Code workers with role-based prompts, a dependency DAG, and an auditable ledger.

```bash
./fleet doctor              # verify the workforce is ready
./fleet roles               # list worker roles
./fleet run <batch>         # execute a batch from .fleet/batches/
./fleet report <batch>      # read what the workers reported
```

The same role definitions are synced to `.claude/agents/`, so an interactive
session can delegate to `adk-agent-engineer`, `sandbox-engineer`, `qa-verifier`,
and the rest by name.
