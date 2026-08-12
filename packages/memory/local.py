"""A local, file-backed Memory Bank used for tests and offline runs.

Real enough to exercise the recall path — persistence, replacement, migration
history — without credentials or a network. It is a fake, not a mock: the
behaviour under test is this implementation's, so a caller that works against it
works against the Agent Platform adapter implementing the same Protocol.

Not a production backend. It has no concurrency control and no retention policy.
"""

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

from packages.memory.profile import PreviousMigration, RepositoryProfile


class LocalMemoryBank:
    """In-memory store, optionally persisted to a single JSON file."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._profiles: dict[str, RepositoryProfile] = {}
        if self._path is not None and self._path.exists():
            self._load()

    def recall(self, repo: str) -> RepositoryProfile | None:
        return self._profiles.get(repo)

    def remember(self, profile: RepositoryProfile) -> None:
        self._profiles[profile.repo] = profile
        self._flush()

    def record_migration(self, repo: str, migration: PreviousMigration) -> None:
        """Append a migration outcome, creating an empty profile if needed.

        History is append-only here: an earlier rejection stays visible even
        after a later attempt succeeds, because the reason it was rejected is
        the part worth recalling.
        """
        existing = self._profiles.get(repo) or RepositoryProfile(repo=repo)
        self._profiles[repo] = replace(
            existing, previous_migrations=(*existing.previous_migrations, migration)
        )
        self._flush()

    def forget(self, repo: str) -> bool:
        existed = self._profiles.pop(repo, None) is not None
        if existed:
            self._flush()
        return existed

    def __len__(self) -> int:
        return len(self._profiles)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._profiles))

    def _load(self) -> None:
        assert self._path is not None
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._profiles = {repo: RepositoryProfile.from_dict(record) for repo, record in raw.items()}

    def _flush(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {repo: profile.to_dict() for repo, profile in sorted(self._profiles.items())}
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
