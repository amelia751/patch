# PatchAPI

**Dependabot for APIs.** When an external API changes, PatchAPI finds the
affected code, generates and verifies a migration in an isolated environment,
and opens an evidence-backed pull request for normal human review.

Built for the [All Things Agentic Hackathon](https://allthingsagentichackathon.devpost.com/)
— Fortified Enterprise Fleet track.

Flagship demo: pinned fork of [`remorses/egaki`](https://github.com/remorses/egaki),
Google Imagen 4 → Gemini 3.1 Flash Image. Second demo:
[`amelia751/storygen`](https://github.com/amelia751/storygen).

## How it works

![PatchAPI architecture](docs/architecture.png)

Three lanes share one Postgres store and stop at a pull request.

**Provider.** Google Cloud service endpoints and release notes feed a Cloud Run
+ ADK job (`patchapi-agents`). The Change Intelligence Agent writes a Change
Manifest. Provider text is untrusted; Model Armor screens intake.

**Developer.** A GitHub App imports a repository into the Next.js console
(`patchapi-web`). Identity Platform handles sign-in. The console talks to the
FastAPI control plane (`patchapi-api`) over SSE. Import and push events go
through Pub/Sub to `patchapi-indexer`, which scans with Zoekt and ast-grep and
stores findings as Needs you, Watching, or Dismissed.

**Agent fleet.** Starting remediation hands the finding to
`patchapi-remediate-worker` (Cloud Run worker pool, ADK + Vertex, Gemini 3.5
Flash). A Patch Agent proposes a change; a separate Verification Agent grades
it. Generated code runs only in a GKE Agent Sandbox under gVisor. Secrets stay
in Secret Manager. A passing run opens a GitHub pull request.

## Live

| | URL |
|---|---|
| Console | https://patchapi-web-913371146929.us-central1.run.app |
| Control API | https://patchapi-api-913371146929.us-central1.run.app |
| Repo indexer | https://patchapi-indexer-913371146929.us-central1.run.app |
| GitHub webhook | https://patchapi-api-913371146929.us-central1.run.app/v1/github/webhooks |

GCP project `patch-505223`, region `us-central1`. Push to `main` deploys via
`.github/workflows/deploy-cloud-run.yml`.

Local: `http://localhost:3000` (console) and `http://localhost:8080` (API).

## Hard boundary

PatchAPI **stops at the pull request**. It does not merge, deploy, edit branch
protection, rotate secrets, or bypass CODEOWNERS / CI.

- Google ADK only for agent orchestration — no LangChain, LangGraph, or other
  third-party agent frameworks on the product path.
- Gemini 3.5 Flash (or newer) for agent reasoning.
- Generated code runs only in isolation. The patch-producing model does not
  grade its own work.
- Postgres is authoritative workflow state. Memory Bank holds institutional
  context, not run status.
- Agents never hold GitHub tokens. They call a narrow tool service with no
  merge, admin, secret, or branch-protection APIs.

## Layout

```
apps/web/                 Next.js console
services/control_api/     FastAPI control plane
services/github_tools/    Narrow GitHub App adapter
services/repo_indexer/    Zoekt + ast-grep inventory
services/agent_runner/    Remediation worker
agents/                   ADK orchestrator + specialists
packages/                 Shared schemas, policy, events, memory
skills/                   Provider migration skills
sandbox/                  GKE Agent Sandbox image
db/                       Migrations and seeds
infra/terraform/          GCP provisioning
demo/                     Egaki baseline and fixtures
docs/                     Architecture and operations
```

## Docs

| | |
|---|---|
| Design of record | [`roadmap.md`](./roadmap.md) |
| Local and cloud setup | [`setup.md`](./setup.md) |
| Architecture | [`docs/architecture.md`](./docs/architecture.md) |
| Provider ingest | [`provider.md`](./provider.md) |
| Conventions | [`CLAUDE.md`](./CLAUDE.md) |
