# services/repo_indexer

Maintains PatchAPI's **API usage inventory** (roadmap §11). When a provider
retires an identifier, impact analysis is an index lookup against this
inventory rather than a clone-and-grep across every repository in the fleet.

This service is **Layer A only**: literal, case-sensitive identifier search with
a stable ordering. No model runs here, so the same commit always produces the
same inventory. Layers B (syntax-aware) and C (Gemini semantic analysis) read
what this service produces; they never replace it.

## What it produces

`ApiUsageInventory` — one `ApiUsageRecord` per occurrence, shaped column-for-column
to the `provider_usages` table in `db/migrations/0003_api_usage_inventory.sql`:

| Field | Meaning |
|---|---|
| `identifier` | the exact watched string, e.g. `imagen-4.0-generate-001` |
| `file_path`, `line_start`, `line_end` | where it was found, repo-relative |
| `usage_kind` | `runtime_source`, `configuration`, `test`, `documentation_example`, … |
| `detection_layer` | always `A_DETERMINISTIC` from this service |
| `confidence` | `1.0` — a literal match is certain |
| `excerpt` | the matching line, truncated; a pointer, not a source channel |

The document carries no timestamp. Two indexes of the same commit serialize to
identical bytes; when a row was first or last seen belongs to Postgres.

## Usage

```bash
# Full index of a checkout, using the pinned Google watchlist.
uv run --package patchapi-repo-indexer python -m patchapi_repo_indexer \
  --root demo/storygen/checkout \
  --repository amelia751/storygen \
  --sha c5428cdcdcd12204e1f4cc47c393dc6e738d88b2 \
  --out /tmp/usages.json

# Push-driven update: only the files a webhook says changed. The result is
# marked `scope: changed_paths` so it is never read as the whole repository.
uv run --package patchapi-repo-indexer python -m patchapi_repo_indexer \
  --root . --repository amelia751/storygen --sha <sha> \
  --changed-path src/image.ts

# Cloud Run worker (Pub/Sub push). Two repositories queue independently.
uv run --package patchapi-repo-indexer patchapi-repo-indexer-serve
```

The live worker is `patchapi-indexer` on Cloud Run. GitHub `push` and console
import publish to Pub/Sub; this service is the subscriber. Same
`(repository, branch)` is serialized; different repositories run in parallel.

An inventory with no usages is a successful run — that repository does not use
the watched identifiers. Only a scan that could not be performed exits non-zero.

## Fail-closed behaviour

- An unknown provider raises `UnknownProviderError` rather than returning an
  empty watchlist, which would report every repository as unaffected.
- An explicitly supplied but empty identifier list is refused for the same reason.
- A changed path that escapes the scan root raises `UnsafePathError`. Webhook
  payloads are external input.
- A missing or non-directory scan root raises `ScanRootError`.
- Unreadable and oversized files are skipped, never guessed at.
- Vendored and build directories (`node_modules/`, `vendor/`, `dist/`, …) are not
  descended into: they are not the customer's API usage.

## Verify

```bash
./scripts/verify_services_repo_indexer.sh
```

Lints and unit-tests the tree, then runs the real CLI against
`tests/fixtures/repo_with_imagen/` and asserts the Imagen 4 identifiers are
found at the expected paths, that the vendored copy is absent, that a tree with
no watched identifiers yields an empty inventory, and that two runs produce
byte-identical output.
