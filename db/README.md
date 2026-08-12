# `db/` — authoritative workflow state

Postgres holds the deterministic truth about PatchAPI runs: what state a run is
in, which external actions have already happened, what policy decided, what the
sandbox produced, and who verified it. Memory Bank holds institutional context
across weeks and is **not** consulted for any of the above (roadmap §10.1).

## Layout

| Path | Purpose |
|---|---|
| `docker-compose.yml` | Local Postgres 16. The only Postgres service definition in the repo. |
| `migrations/` | Forward-only `NNNN_slug.sql` scripts. Never edited after they apply. |
| `seeds/` | Re-runnable demo data, clearly labelled as seed. |
| `src/patchapi_db/` | Discovery, checksumming, and application of the scripts above. |
| `tests/` | Offline checks on the SQL corpus; no database required. |

## Running it

```bash
docker compose -f db/docker-compose.yml up -d

export PYTHONPATH=db/src                # the runner is stdlib-only; no install needed
uv run python -m patchapi_db migrate    # apply pending migrations
uv run python -m patchapi_db seed       # (re-)apply demo seed data
uv run python -m patchapi_db status     # exits 1 if anything is pending
uv run python -m patchapi_db sql        # run a SQL script from stdin

./scripts/verify_db.sh                  # the full dynamic check
```

`uv run --package patchapi-db python -m patchapi_db …` works too, and installs
the member into the shared workspace environment. The `PYTHONPATH` form above
is used by the verifier so that running it does not change what other trees in
the workspace have installed.

The runner has no database driver dependency: it discovers and orders the SQL,
then hands it to `psql`. With `DATABASE_URL` set it uses a local `psql` client
against that DSN — the Cloud SQL path, via the Auth Proxy. With `DATABASE_URL`
unset it runs `psql` inside the compose container, so a developer needs Docker
but not a matching client install.

## Migration rules

1. **Forward-only.** To change an applied migration, add a new one. The runner
   records a SHA-256 of every migration and refuses to continue if the text of
   an applied one has changed.
2. **One concern per file.** The version is the four-digit filename prefix and
   determines apply order; versions are contiguous from `0001`.
3. **No transaction control inside a script.** The runner wraps each script and
   its ledger row in one transaction, so a failed migration leaves nothing.
4. **No business logic in triggers.** Every state change an agent makes must be
   visible in that agent's trace, not hidden in the database. The only
   database-side logic is `CHECK` constraints, and each one encodes a product
   rule rather than a workflow step.

## Constraints that encode product rules

These are enforced by the schema so a miswired or prompt-injected agent cannot
record the thing the rule forbids. `scripts/verify_db.sh` proves each of them
still rejects the write it is supposed to reject.

| Constraint | Rule |
|---|---|
| `policy_decisions_never_auto_merge` | PatchAPI stops at the pull request. |
| `pull_requests_never_self_merged` | Any merge came from a human, through CODEOWNERS. |
| `verification_results_independent_verifier` | The patching agent cannot grade its own patch. |
| `patch_attempts_success_ran_in_sandbox` | A succeeded attempt has an isolated run with exit code 0. |
| `remediation_runs_terminal_has_ended_at` | A run is either live or finished, never both. |
| `policy_decisions_blocked_authorizes_nothing` | A BLOCKED verdict authorizes no patching or PR. |
| `audit_events_denied_has_reason` | A denial records why it was denied. |

## Idempotency

`external_action_keys` is keyed on `run_id + action_type + base_sha`
(roadmap §9). A row is `CLAIMED` before an external call and `COMPLETED` after,
so a process that crashes between the two resumes with the fact visible rather
than repeating a pull request or a sandbox allocation.

## Seed data

`seeds/0001_demo_egaki.sql` populates the pinned Egaki scenario from
`demo/fixtures/google-imagen4-deprecation.json`, `demo/egaki/baseline.json`, and
`demo/egaki/artifacts/imagen-inventory.json`. Every seeded row uses a UUID in
the reserved `5eedda7a-` prefix, and the seeded pull request URL is on
`example.invalid` — no pull request has been opened.
