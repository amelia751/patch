# `packages/memory`

The Memory Bank client interface from `roadmap.md` §10.2, plus `LocalMemoryBank`
— a file-backed fake for tests and offline runs.

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

Agents depend on the `MemoryBankClient` Protocol, so the Agent Platform adapter
and this fake are interchangeable and nothing in the runtime path needs
credentials in order to import.

Verified by `./scripts/verify_packages_remaining.sh`.
