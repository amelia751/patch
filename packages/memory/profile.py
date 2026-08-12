"""The institutional context PatchAPI recalls about a repository (roadmap §10.2).

This is the knowledge that is expensive to rediscover weeks later: which team
owns a repo, that a previous migration was rejected and why, which commands are
the canonical build and test, which paths the org has already said no to.

It is explicitly **not** workflow state. Run status, idempotency, and audit live
in Postgres (§10.1); a `RepositoryProfile` may be stale, incomplete, or absent
without the run's correctness depending on it.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class PreviousMigration:
    """The outcome of an earlier attempt at a related change."""

    migration_id: str
    decision: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.migration_id,
            "decision": self.decision,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> Self:
        return cls(
            migration_id=str(record["id"]),
            decision=str(record["decision"]),
            reason=str(record.get("reason", "")),
        )


@dataclass(frozen=True, slots=True)
class RepositoryProfile:
    """Recalled context for one repository.

    Every field has a benign default: a missing profile must degrade to "we know
    nothing about this repository", never to an assumption that something was
    already approved.
    """

    repo: str
    owner_team: str = ""
    criticality: str = "unknown"
    provider_dependencies: tuple[str, ...] = ()
    approval_rules: tuple[str, ...] = ()
    previous_migrations: tuple[PreviousMigration, ...] = ()
    known_exceptions: tuple[str, ...] = ()
    canonical_test_commands: tuple[str, ...] = ()
    prohibited_paths: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default=())

    @property
    def requires_human_review(self) -> bool:
        """True when the org has recorded a standing human-review requirement."""
        return "human_review_required" in self.approval_rules

    def rejected_migrations(self) -> tuple[PreviousMigration, ...]:
        """Earlier attempts a human turned down.

        Recalling these is the point of institutional memory: a change that was
        rejected in May should not be re-proposed in August as if it were new.
        """
        return tuple(m for m in self.previous_migrations if m.decision == "rejected")

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "owner_team": self.owner_team,
            "criticality": self.criticality,
            "provider_dependencies": list(self.provider_dependencies),
            "approval_rules": list(self.approval_rules),
            "previous_migrations": [m.to_dict() for m in self.previous_migrations],
            "known_exceptions": list(self.known_exceptions),
            "canonical_test_commands": list(self.canonical_test_commands),
            "prohibited_paths": list(self.prohibited_paths),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> Self:
        def as_tuple(key: str) -> tuple[str, ...]:
            value: Sequence[Any] = record.get(key) or ()
            return tuple(str(item) for item in value)

        return cls(
            repo=str(record["repo"]),
            owner_team=str(record.get("owner_team", "")),
            criticality=str(record.get("criticality", "unknown")),
            provider_dependencies=as_tuple("provider_dependencies"),
            approval_rules=as_tuple("approval_rules"),
            previous_migrations=tuple(
                PreviousMigration.from_dict(item)
                for item in record.get("previous_migrations") or ()
            ),
            known_exceptions=as_tuple("known_exceptions"),
            canonical_test_commands=as_tuple("canonical_test_commands"),
            prohibited_paths=as_tuple("prohibited_paths"),
            notes=as_tuple("notes"),
        )
