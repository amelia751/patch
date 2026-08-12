"""Memory Bank client interface and local fake (roadmap §10.2).

Institutional context across weeks — owning team, prior migration decisions,
canonical test commands, standing prohibitions. Never the source of truth for
run status, idempotency, or audit; those live in Postgres (§10.1).
"""

from packages.memory.client import MemoryBankClient, MemoryUnavailableError
from packages.memory.local import LocalMemoryBank
from packages.memory.profile import PreviousMigration, RepositoryProfile

__all__ = [
    "LocalMemoryBank",
    "MemoryBankClient",
    "MemoryUnavailableError",
    "PreviousMigration",
    "RepositoryProfile",
]
