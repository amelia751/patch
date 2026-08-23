"""The corpus row a run is about, in the shape the patch loop already reads.

The orchestrator seeds a slice from a `ChangeManifest`, obtained either by
crawling a notice feed or by loading a pinned JSON file. Neither fits a run
started from the console: the notice was normalized weeks ago and the answer is
already in `change_events`, where Change Intelligence put it.

Rebuilding the manifest from that row rather than re-reading the provider is
deliberate. A remediation must act on the change the operator saw and approved
on the card, not on whatever the provider's page says by the time the job runs.
It also means the patch lane never touches untrusted provider text at all — it
consumes a normalized, already-adjudicated record.

The corpus stores `change_kind`, a coarser vocabulary than the manifest's
`change_type`, so the inverse mapping loses a distinction. That is tolerable
here: downstream, `change_type` selects framing and whether an effective date is
required, and every kind maps to a member of its own family.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from packages.schemas.change_manifest import ChangeManifest
from packages.state import snapshots

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

# The inverse of `packages.state.corpus._CHANGE_KIND_BY_TYPE`. Deprecation maps
# to model retirement because that is what the corpus overwhelmingly holds, and
# because it is the stricter reading: it requires an effective date, so a row
# without one is rejected here rather than patched against an undated deadline.
_TYPE_BY_KIND: Final[dict[str, str]] = {
    "deprecation": "model_retirement",
    "replacement": "model_retirement",
    "breaking_change": "breaking_change",
    "change": "behavior_change",
}

_FALLBACK_SOURCE: Final[str] = "https://ai.google.dev/gemini-api/docs/deprecations"

_EVENT_SQL: Final[str] = """
SELECT
    ce.external_id, ce.provider, ce.change_kind::text AS change_kind,
    ce.severity::text AS severity, ce.announced_at, ce.effective_at,
    ce.affected_identifiers, ce.source_urls, ce.migration, ce.title, ce.summary,
    (
        SELECT i.identifier FROM change_event_identifiers i
        WHERE i.change_event_id = ce.id AND i.role = 'replacement' LIMIT 1
    ) AS recommended_replacement
FROM change_events ce
WHERE ce.id = $1
"""

_PER_IDENTIFIER_SQL: Final[str] = """
SELECT identifier, replacement, semantic
FROM change_event_identifiers
WHERE change_event_id = $1 AND role = 'retired' AND replacement IS NOT NULL
"""


class ManifestUnavailableError(RuntimeError):
    """The corpus row cannot be expressed as a manifest a run may act on."""


async def load(connection: asyncpg.Connection, change_event_id: UUID | str) -> ChangeManifest:
    """Build the manifest for one corpus row.

    Raises rather than filling gaps. A change with no affected identifiers, or a
    retirement with no effective date, is a row Change Intelligence did not
    finish — and inventing the missing part would have the patch lane act on a
    deprecation nobody established.
    """
    identifier = (
        change_event_id if isinstance(change_event_id, UUID) else UUID(str(change_event_id))
    )
    row = await connection.fetchrow(_EVENT_SQL, identifier)
    if row is None:
        raise ManifestUnavailableError(f"no change event {change_event_id}")

    affected = [name for name in (row["affected_identifiers"] or []) if name]
    if not affected:
        raise ManifestUnavailableError(
            f"{row['external_id']} names no affected identifier, so there is nothing to migrate"
        )

    replacement = row["recommended_replacement"]
    if replacement in affected:
        # A notice that both retires and recommends the same string is a
        # normalization error, not a migration target.
        replacement = None

    per_identifier = [
        {
            "identifier": entry["identifier"],
            "replacement": entry["replacement"],
            "semantic_migration_required": bool(entry["semantic"]),
        }
        for entry in await connection.fetch(_PER_IDENTIFIER_SQL, identifier)
        if entry["identifier"] in affected and entry["replacement"] not in affected
    ]

    payload: dict[str, Any] = {
        "provider": row["provider"],
        "change_id": row["external_id"],
        "change_type": _TYPE_BY_KIND.get(row["change_kind"], "behavior_change"),
        "severity": row["severity"],
        "announced_at": row["announced_at"],
        "effective_at": row["effective_at"],
        "affected_identifiers": affected,
        "recommended_replacement": replacement,
        "semantic_migration_required": row["migration"] == "semantic",
        "per_identifier": per_identifier,
        "source_urls": list(row["source_urls"] or []) or [_FALLBACK_SOURCE],
        # Policy fails closed without these. Carrying whatever was captured —
        # possibly nothing — keeps that gate meaningful: a change nobody
        # snapshotted still reaches policy as an unproven claim.
        "source_snapshots": [
            snapshot.model_dump(mode="json")
            for snapshot in await snapshots.load(connection, identifier)
        ],
    }
    try:
        return ChangeManifest.model_validate(payload)
    except ValueError as exc:
        raise ManifestUnavailableError(
            f"{row['external_id']} cannot be expressed as a ChangeManifest: {exc}"
        ) from exc


def write(manifest: ChangeManifest, directory: Path) -> Path:
    """Persist the manifest where `seed_static_manifest` can read it.

    Going through a file rather than adding a fourth seeding path keeps one
    code path between "here is the change" and "the run is NORMALIZED", which is
    the path the smoke test already exercises.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "change_manifest.json"
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8"
    )
    return path


__all__ = ["ManifestUnavailableError", "load", "write"]
