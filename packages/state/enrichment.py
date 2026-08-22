"""Where the Change Intelligence agent is allowed to write.

The deterministic lane owns whether a release needs you. It reaches that answer
from evidence a model can neither improve nor argue with: a live check that 404s,
an identifier the indexer found in an imported tree, a date on a pinned feed.
That answer must not move because a model phrased something confidently.

The agent owns the part determinism is bad at — reading a notice, and saying in
a sentence why this break matters to this repository and what to move to.

So the split is enforced in SQL rather than in a prompt. `_ENRICH_SQL` names
four columns. `severity`, `change_kind`, `fail_closed`, `false_positive`,
`effective_at`, and `announced_at` are absent from the statement, and
`project_change_findings` is never touched here at all, so no agent output can
reclassify a finding. Naming a replacement does not clear `fail_closed`: a
proposal is not a verification, and the finding stays in Need you until a human
or the patch pipeline acts on it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

MAX_SUMMARY_CHARS: Final[int] = 400

# Only these four columns. See the module docstring before adding a fifth.
_ENRICH_SQL: Final[str] = """
UPDATE change_events
SET summary = COALESCE(NULLIF($2, ''), summary),
    replacements = CASE
        WHEN jsonb_array_length($3::jsonb) > 0 THEN $3::jsonb
        ELSE replacements
    END,
    migration = COALESCE($4, migration),
    source_urls = (
        SELECT COALESCE(array_agg(DISTINCT url), '{}'::text[])
        FROM unnest(source_urls || $5::text[]) AS url
        WHERE url <> ''
    )
WHERE external_id = $1
"""

_EVENT_FOR_IDENTIFIER_SQL: Final[str] = """
SELECT external_id
FROM change_events
WHERE provider = $1 AND $2 = ANY(affected_identifiers)
ORDER BY detected_at DESC
LIMIT 1
"""


async def event_for_identifier(
    connection: asyncpg.Connection, *, provider: str, identifier: str
) -> str | None:
    """The most recent change event naming `identifier`, if one exists."""
    row = await connection.fetchrow(_EVENT_FOR_IDENTIFIER_SQL, provider, identifier)
    return None if row is None else str(row["external_id"])


async def apply_agent_rationale(
    connection: asyncpg.Connection,
    *,
    external_id: str,
    rationale: str = "",
    replacement: str | None = None,
    replaced_identifier: str = "",
    migration: str | None = None,
    source_urls: list[str] | None = None,
) -> bool:
    """Attach agent reasoning to an existing event. Cannot change its status.

    Returns whether a row was updated. A missing event is not an error: the
    deterministic lane may not have recorded one yet, and the agent must not
    conjure a release that no evidence supports.
    """
    if migration not in (None, "mechanical", "semantic"):
        raise ValueError(f"unknown migration kind {migration!r}")

    replacements: list[dict[str, str]] = []
    if replacement and replaced_identifier:
        replacements = [
            {"from": replaced_identifier, "to": replacement, "notes": "proposed by analysis"}
        ]

    status = await connection.execute(
        _ENRICH_SQL,
        external_id,
        rationale.strip()[:MAX_SUMMARY_CHARS],
        replacements,
        migration,
        list(source_urls or []),
    )
    updated = not status.endswith(" 0")
    if updated:
        log.info("attached rationale to %s", external_id)
    else:
        log.info("no change event named %s; rationale dropped", external_id)
    return updated


async def enrich_from_manifest(connection: asyncpg.Connection, payload: dict[str, Any]) -> bool:
    """Route a recorded ChangeManifest to the event the deterministic lane wrote.

    The agent picks its own `change_id`, which will not match the
    `probe:<surface>:<identifier>` id the deterministic lane used. Matching on
    the affected identifier instead keeps one release on one card rather than
    producing a second row that says the same thing in nicer prose.
    """
    identifiers = [
        str(item).strip()
        for item in (payload.get("affected_identifiers") or [])
        if str(item).strip()
    ]
    if not identifiers:
        return False
    provider = str(payload.get("provider") or "google")
    external_id = await event_for_identifier(
        connection, provider=provider, identifier=identifiers[0]
    )
    if external_id is None:
        return False
    replacement = str(payload.get("recommended_replacement") or "").strip() or None
    return await apply_agent_rationale(
        connection,
        external_id=external_id,
        rationale=str(payload.get("rationale") or payload.get("summary") or ""),
        replacement=replacement,
        replaced_identifier=identifiers[0],
        migration=("semantic" if payload.get("semantic_migration_required") else "mechanical")
        if replacement
        else None,
        source_urls=[
            str(item).strip() for item in (payload.get("source_urls") or []) if str(item).strip()
        ],
    )


__all__ = [
    "apply_agent_rationale",
    "enrich_from_manifest",
    "event_for_identifier",
]
