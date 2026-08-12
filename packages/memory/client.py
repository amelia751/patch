"""The Memory Bank client interface (roadmap §10.2).

Two implementations are expected: one backed by the Gemini Enterprise Agent
Platform Memory Bank, and `LocalMemoryBank` for offline runs and tests. Agents
depend on this Protocol, so nothing in the runtime path needs credentials to be
importable, and a memory outage degrades a run rather than failing it.

Memory Bank is institutional context, not transactional truth. That constraint
is encoded here: `recall` returns `None` for an unknown repository, and callers
must treat that as "we know nothing", never as "nothing was prohibited".
"""

from typing import Protocol, runtime_checkable

from packages.memory.profile import PreviousMigration, RepositoryProfile


class MemoryUnavailableError(RuntimeError):
    """The memory backend could not be reached.

    Callers decide whether to proceed without context. They must not silently
    substitute an empty profile for a failed lookup — a repository whose
    prohibitions could not be read is not a repository with no prohibitions.
    """


@runtime_checkable
class MemoryBankClient(Protocol):
    """Read and write institutional context about a repository."""

    def recall(self, repo: str) -> RepositoryProfile | None:
        """Return the stored profile for `repo`, or `None` if none exists."""
        ...

    def remember(self, profile: RepositoryProfile) -> None:
        """Store or replace the profile for `profile.repo`."""
        ...

    def record_migration(self, repo: str, migration: PreviousMigration) -> None:
        """Append the outcome of a migration attempt to `repo`'s history."""
        ...

    def forget(self, repo: str) -> bool:
        """Remove the profile for `repo`. Returns whether one existed."""
        ...
