# `packages/memory`

The Memory Bank client interface from `roadmap.md` §10.2, with two
implementations: `VertexMemoryBank` against a Vertex AI Agent Engine, and
`LocalMemoryBank`, a file-backed fallback for tests and offline runs.

Memory Bank holds institutional context: who owns a repository, that a related
migration was rejected in May and why, which commands are the canonical build
and test, which paths the org has already ruled out. It is **not** workflow
state — run status, idempotency, and audit are Postgres's job (§10.1).

That constraint shows up in the interface: `recall()` returns `None` for an
unknown repository, and a backend failure raises `MemoryUnavailableError` rather
than returning an empty profile. A repository whose prohibitions could not be
read is not a repository with no prohibitions.

```python
from packages.memory import LocalMemoryBank, RepositoryProfile

bank = LocalMemoryBank(path="/tmp/patchapi-memory.json")
bank.remember(RepositoryProfile(repo="amelia751/egaki", approval_rules=("human_review_required",)))
bank.recall("amelia751/egaki").requires_human_review  # True
bank.recall("someone/unknown")                        # None
```

Agents depend on the `MemoryBankClient` Protocol, so the two implementations are
interchangeable and nothing in the runtime path needs credentials in order to
import. They are not equivalent, though: `LocalMemoryBank` stores profiles only
and implements no `recall_migrations`, so a run on the local fallback recalls
what the profile records and none of the prose migration history. `recall` in
`agents/memory.py` treats the method as optional for exactly that reason.

## `VertexMemoryBank`

```python
from packages.memory import VertexMemoryBank, memory_bank_unavailable_reason

if memory_bank_unavailable_reason() is None:
    bank = VertexMemoryBank.from_env()
```

Configured by `PATCHAPI_MEMORY_BANK_ENGINE` — either the bare engine id or a
full `projects/.../reasoningEngines/...` name — and `PATCHAPI_MEMORY_BANK_LOCATION`
(default `us-central1`). Agent Engine is regional and the engine id is an opaque
number, so both are configuration. `agents/memory.py` is the seam: it opens
whichever bank is configured and reports the reason when none is.

Deliberately not the `google-cloud-aiplatform` SDK. This package is imported by
the agent lane and the REST surface it needs is four calls, so `google-auth` for
credentials and the standard library for transport keeps the dependency that
reaches production small enough to audit.

Two kinds of memory live under one repository scope, kept apart because they are
consumed differently — a scope is an exact-match partition, so a recall query
that stops matching what a write produced fails *silently*, returning "we know
nothing about this repository" instead of an error. That is why the scope keys
and fact kinds are pinned in `config.py` rather than written at call sites.

| Kind | Stored as | Retrieved by |
|---|---|---|
| `repository_profile` | one JSON fact behind a version marker | exact scope; parsed into `RepositoryProfile` |
| `previous_migration` | one prose sentence per outcome | semantic similarity, because a run months later asks "was something like this tried here before" and a JSON blob is not what that matches against |

A memory that does not parse is skipped with a warning rather than raised on: the
engine is shared institutional storage and one malformed entry must not make a
repository unreadable.

## What this package does not decide

Whether a recollection may be *shown* to an agent, and to which one, is
`agents/memory.py` and `agents/orchestrator.py`. Recalled content is reduced to
prose there and the typed profile is dropped, so no deterministic gate can
branch on a memory; the Verification Agent is never shown one at all. See
`docs/threat-model.md` T13.

Verified by `./scripts/verify_packages_remaining.sh`, and by
`./scripts/verify_agent_image_closure.sh`, which asserts this package is present
in the agent lane image and that a Memory Bank is reachable under the
deployment's environment.
