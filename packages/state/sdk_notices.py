"""SDK facts that are not disappearances, turned into releases.

The poller already handles the package that vanished: `not_found` is a
transition and the event pipeline carries it. Two other registry facts break
callers and neither is a transition.

*The author deprecated it.* `@google/generative-ai` still installs and still
resolves; npm simply carries a message saying to move to `@google/genai`. A
liveness check reports that as healthy forever.

*A new major shipped.* That is not a break — a pinned 1.x keeps working — so it
is recorded as `new_identifier`, which classification treats as watching rather
than as something owed action. It is only worth a card when nothing indexed has
adopted it yet: if any usage already pins the new major, somebody knows, and a
card for the stragglers would be noise on a migration already underway.

The pinned major is read from the usage excerpt, which is the manifest line the
indexer stored (`"@google/genai": "^1.4.0"`). No schema change buys it, and a
constraint the reviewer can see beats one PatchAPI inferred.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from packages.providers.sdk import (
    PackageRelease,
    fetch_packages,
    is_sdk_identifier,
    major_of,
    split_sdk_identifier,
)
from packages.state.watchlist import WatchlistNote

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

_SDK_USAGES_SQL: Final[str] = """
SELECT identifier, excerpt
FROM provider_usages
WHERE provider = $1 AND retired_at IS NULL
"""

_REGISTRY_DOCS: Final[dict[str, str]] = {
    "npm": "https://www.npmjs.com/package",
    "pypi": "https://pypi.org/project",
    "go": "https://pkg.go.dev",
}


def registry_page(ecosystem: str, name: str) -> str:
    """Where a human reads the same thing the liveness check read."""
    base = _REGISTRY_DOCS.get(ecosystem, "")
    return f"{base}/{name}" if base else ""


def _sources(release: PackageRelease) -> list[str]:
    page = registry_page(release.ecosystem, release.name)
    return [url for url in (page, release.source_url) if url]


def deprecation_note(identifier: str, release: PackageRelease) -> WatchlistNote | None:
    """The registry says this package is deprecated, and quotes the author."""
    if not release.deprecated:
        return None
    return {
        "external_id": f"sdk:deprecated:{identifier}",
        "provider": "google",
        "product": identifier,
        "change_kind": "deprecation",
        "severity": "high",
        "title": f"{release.name} is deprecated on {release.ecosystem}",
        "summary": (
            f"The {release.ecosystem} registry marks {release.name} as deprecated. "
            f"The package author says: {release.deprecated.strip()[:200]}"
        ),
        "source_urls": _sources(release),
        "identifiers": [identifier],
        "replacements": [],
        "announced_at": None,
        "effective_at": None,
        # A deprecated package still installs. Naming a successor is reading the
        # author's sentence, which is Change Intelligence's job, not a parse.
        "fail_closed": False,
        "false_positive": False,
        "migration": None,
    }


def major_note(
    identifier: str, release: PackageRelease, pinned_majors: set[int]
) -> WatchlistNote | None:
    """A major nobody has adopted yet, or None when there is nothing to say."""
    latest = release.latest_major
    if latest is None or not pinned_majors or latest <= max(pinned_majors):
        return None
    behind = ", ".join(str(major) for major in sorted(pinned_majors))
    return {
        "external_id": f"sdk:major:{identifier}:{latest}",
        "provider": "google",
        "product": identifier,
        "change_kind": "new_identifier",
        "severity": "medium",
        "title": f"{release.name} {latest}.x is published",
        "summary": (
            f"{release.ecosystem} now publishes {release.name} at {release.latest}. "
            f"Indexed manifests pin major {behind}. A pinned major keeps installing, "
            "so nothing is broken; adopting the new one is a decision, not a repair."
        ),
        "source_urls": _sources(release),
        "identifiers": [identifier],
        "replacements": [],
        "announced_at": None,
        "effective_at": None,
        "fail_closed": False,
        "false_positive": False,
        "migration": None,
    }


async def indexed_sdk_usages(
    connection: asyncpg.Connection, provider: str
) -> dict[str, set[int]]:
    """Every SDK identifier in the index, with the majors its manifests pin."""
    rows = await connection.fetch(_SDK_USAGES_SQL, provider)
    found: dict[str, set[int]] = {}
    for row in rows:
        identifier = str(row["identifier"] or "")
        if not is_sdk_identifier(identifier):
            continue
        majors = found.setdefault(identifier, set())
        split = split_sdk_identifier(identifier)
        excerpt = str(row["excerpt"] or "")
        # The name repeats inside the excerpt and can carry digits of its own
        # (`@google/generative-ai`), so the constraint is what follows it.
        if split is not None:
            _, name = split
            excerpt = excerpt.split(name, 1)[-1] if name in excerpt else excerpt
        major = major_of(excerpt)
        if major is not None:
            majors.add(major)
    return found


async def ensure_sdk_events(connection: asyncpg.Connection, provider: str) -> int:
    """Write registry notices for the SDKs this fleet depends on. Returns the count.

    Provider-wide rather than per project: a registry answer is the same for
    everyone, and the per-project part is the inventory join that classification
    already does.
    """
    from packages.state.inbox_corpus import _insert_notes

    usages = await indexed_sdk_usages(connection, provider)
    if not usages:
        return 0
    releases = await fetch_packages(sorted(usages))
    notes: list[WatchlistNote] = []
    for identifier, majors in sorted(usages.items()):
        release = releases.get(identifier)
        if release is None or not release.exists:
            # Unreachable, or gone. Gone is the poller's transition to announce.
            continue
        for note in (
            deprecation_note(identifier, release),
            major_note(identifier, release, majors),
        ):
            if note is not None:
                notes.append(note)
    written = await _insert_notes(connection, notes)
    if written:
        log.info("recorded %d sdk notices for %s", written, provider)
    return written


__all__ = [
    "deprecation_note",
    "ensure_sdk_events",
    "indexed_sdk_usages",
    "major_note",
    "registry_page",
]
