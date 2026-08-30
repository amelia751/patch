# patchapi-github-tools

The narrow GitHub App capability adapter (roadmap §7.3, §14).

This service owns the GitHub App private key so that agents and sandboxes never
do. Agents receive **capabilities**, never tokens: they name an operation, this
service decides whether that name is exposed at all, whether the calling agent
holds it, and only then talks to GitHub.

## The surface

Everything goes through one choke point:

```text
GET  /healthz                             liveness
GET  /readyz                              ready only when the App is wired
GET  /v1/capabilities                     the catalog, the grants, the boundary
POST /v1/capabilities/{capability_name}   invoke one capability
POST /mcp                                 the same capabilities over MCP JSON-RPC
```

| Read | Write |
|---|---|
| `get_repository_metadata` | `create_patch_branch` |
| `get_file` | `commit_verified_patch` |
| `list_tree` | `open_pull_request` |
| `get_commit` | `add_pr_comment` |
| `get_pull_request` | |
| `get_checks` | |

**Never exposed:** `merge_pull_request`, `change_branch_protection`,
`modify_actions_secrets`, `modify_repository_admin_settings`,
`delete_repository`, and the rest of `packages.github.FORBIDDEN_CAPABILITIES`.
They are not unimplemented — they are named, refused with a structured 403, and
blocked a second time at the transport by URL shape.

## Order of checks

1. **Identity** — `X-PatchAPI-Agent` names a known agent, or 401.
2. **Allowlist** — the capability is exposed, or 403 (forbidden) / 404 (unknown).
3. **Grant** — that agent holds that capability, or 403. Only `patchapi.pr`
   holds write capabilities; `patchapi.change_intelligence` holds none at all,
   because it reads untrusted provider material (roadmap §8.1).
4. **Credentials** — the App is configured, or 503 saying no call was attempted.
5. **Arguments** — the contract is satisfied, or 422.

Steps 1–3 never reach GitHub. Step 2 does not depend on step 4: an attempt to
merge is refused as forbidden whether or not the App is wired.

Both transports run these checks by calling one function,
`invocation.execute_capability`. There is no second implementation of the order.

## MCP

`POST /mcp` speaks MCP over JSON-RPC 2.0 (`initialize`, `tools/list`,
`tools/call`, `ping`, and `notifications/initialized`) so the service can be
published in an agent catalog and discovered across departments. It is a second
**transport**, not a second surface:

- `tools/call` goes through `execute_capability` — the same gates in the same
  order — so MCP grants no privilege the REST route does not.
- `tools/list` is scoped to the identity in `X-PatchAPI-Agent`. `patchapi.pr`
  sees ten tools, a read-only agent sees six, `patchapi.change_intelligence`
  sees none. A forbidden operation has no descriptor to omit.
- `inputSchema` is generated from the same Pydantic model the REST route
  validates against, with `$ref` inlined for consumers that reject references.
  It cannot drift from the REST contract.
- Annotations state the boundary in MCP's own vocabulary: `readOnlyHint` for the
  six reads, `destructiveHint: false` everywhere (the writes create a branch, a
  commit, a pull request, or a comment — nothing deletes or rewrites history),
  and `idempotentHint` only where a replay genuinely converges.

Authentication stays at the transport: an unrecognised caller gets HTTP 401.
Everything after that is JSON-RPC — a malformed envelope, an unknown method, and
a refused capability all return HTTP 200 with an error object, and each refusal
carries the REST refusal detail verbatim in `error.data`, so both transports
leave the same audit record. Refusal codes are distinct on purpose:

| Code | Meaning |
|---|---|
| `-32001` | forbidden operation — not part of this surface |
| `-32002` | the calling agent does not hold that capability |
| `-32003` | the GitHub App is not configured; no call was attempted |
| `-32004` | the repository moved since verification |
| `-32005` | GitHub refused or failed the call |
| `-32602` | unknown tool, or arguments that fail the contract |

## Write-path guarantees

- Writes only target branches under `patchapi/`. There is no code path that
  commits to `main`.
- Branch creation and commits pin a full 40-character SHA. A branch that moved
  after verification produces a 409, never a commit onto an unverified tree.
- `open_pull_request` is idempotent on (run, base SHA, title): a replay updates
  its own pull request instead of opening a duplicate.
- The pull request body is **rendered from**
  `src/patchapi_github_tools/templates/migration_pr.md`, never supplied. The
  template is the Dependabot-style layout: one-line lead, tables, `<details>`
  for evidence, and a note that **patchbot** cannot merge. Local `file://`
  paths are dropped. Rename the GitHub App display name to `patchbot` so
  comments read `patchbot[bot]` — GitHub always appends that suffix.
- Evidence with a failed verification check is rejected before GitHub is
  contacted (roadmap §8.6, CLAUDE.md §6).

## Credentials

Loaded from the environment, never from the repository:

| Variable | Meaning |
|---|---|
| `GITHUB_APP_ID` | numeric App ID |
| `GITHUB_APP_INSTALLATION_ID` | numeric installation ID |
| `GITHUB_APP_PRIVATE_KEY_PATH` | PEM file, local development (`.secrets/`) |
| `GITHUB_APP_PRIVATE_KEY_SECRET` | Secret Manager resource name, deployed |
| `GITHUB_API_BASE` | optional, for GitHub Enterprise |

Exactly one of the two key sources may be set. The key and every derived
credential are carried in `Secret`, whose `repr`, `str`, and `format` all render
`<redacted>`; the tree contains no logging and no printing, so there is nowhere
for a token to leak into. Upstream error bodies are never forwarded.

Unset credentials are a supported state: the service starts, serves the catalog,
reports itself not ready, and fails every invocation closed.

## Running and verifying

```bash
uv run --package patchapi-github-tools uvicorn patchapi_github_tools.asgi:app --port 8081
./scripts/verify_services_github_tools.sh
```

The verifier lints, unit-tests, boots the app, and probes the boundary over
HTTP. Its final leg reads the demo fork through a real installation token when
App credentials are present, and prints an explicit `SKIP` when they are not. It
is never faked.

## Deployed

`https://patchapi-github-tools-913371146929.us-central1.run.app`, private. The
image is built from `services/github_tools/Dockerfile` by the `github-tools` job
in `.github/workflows/deploy-cloud-run.yml`; the identity, the secret grants, and
the invoker list come from `scripts/bootstrap_github_tools.sh`.

Deployed, the private key is mounted as a file rather than resolved through
`GITHUB_APP_PRIVATE_KEY_SECRET`, so the image needs no Secret Manager client and
the key never passes through application code on its way in.

Only `patchapi-agents` and `patchapi-api` may invoke it. Readiness is `/readyz`,
which reports whether the App installation resolved; `/healthz` is answered by
Google's edge on a `run.app` host and never reaches the container.
