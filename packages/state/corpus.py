"""Writing what a notice means, once, for every subscriber.

`enrichment` attaches a sentence to a row some other lane already created. This
module is the other half of the split: the Change Intelligence agent now reads
a notice upstream of any project and the manifest it produces *is* the corpus
row, together with one row per identifier the notice names.

Two rules hold the design together.

The rationale describes the change, never a repository. One row is shown to
every subscriber, so "no usages in this project" is false for the next reader
and contradicts the inventory rendered beside it. Anything true of one tree
belongs in `change_impacts`, which is scoped to a repository at a commit.

`summary` stays the provider's own words and is never overwritten. Enrichment
used to replace it, which lost what Google actually said and left no way to
show a notice next to a reading of it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from packages.schemas.change_manifest import ChangeManifest

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

MAX_RATIONALE_CHARS: Final[int] = 600

# Bumped when the agent's reading could differ for a notice already read —
# a prompt change, a new tool, a manifest field. Rows below this are stale and
# eligible for re-normalization without re-ingesting the notice.
NORMALIZER_VERSION: Final[str] = "1.0.0"

AGENT: Final[str] = "agent"

# Whether the identifier stops working as written. `behavior_change` is the one
# kind where it does not: the call still resolves and still returns, it just
# answers differently. That is worth watching and is not worth telling somebody
# their code is broken, so those identifiers are mentioned rather than retired.
_NON_RETIRING_CHANGE_TYPES: Final[frozenset[str]] = frozenset({"behavior_change"})

_CHANGE_KIND_BY_TYPE: Final[dict[str, str]] = {
    "model_retirement": "deprecation",
    "endpoint_removal": "deprecation",
    "api_deprecation": "deprecation",
    "breaking_change": "breaking_change",
    "parameter_change": "breaking_change",
    "auth_change": "breaking_change",
    "behavior_change": "change",
}

_UPSERT_EVENT_SQL: Final[str] = """
INSERT INTO change_events (
    external_id, provider, product, change_kind, severity, title, summary,
    source_urls, affected_identifiers, replacements, announced_at, effective_at,
    fail_closed, false_positive, migration,
    notice_id, notice_sha256, provenance, rationale,
    normalizer_version, normalized_at
)
VALUES (
    $1, $2, $3, $4::change_kind, $5::change_severity, $6, $7,
    $8::text[], $9::text[], $10::jsonb, $11::date, $12::date,
    $13, false, $14,
    $15, $16, $17::change_provenance, $18,
    $19, now()
)
ON CONFLICT (provider, external_id) DO UPDATE
-- A caller with nothing better to offer passes the change id, and overwriting
-- "Imagen 4 retirement" with "imagen4-retirement-2026-08-17" would make the
-- card worse for no gain. Only a real title replaces a real one.
SET title                = CASE
        WHEN $6 <> '' AND $6 <> change_events.external_id THEN $6
        ELSE change_events.title
    END,
    product              = CASE
        WHEN $3 <> '' THEN $3 ELSE change_events.product
    END,
    change_kind          = EXCLUDED.change_kind,
    severity             = EXCLUDED.severity,
    affected_identifiers = EXCLUDED.affected_identifiers,
    replacements         = EXCLUDED.replacements,
    announced_at         = COALESCE(EXCLUDED.announced_at, change_events.announced_at),
    effective_at         = COALESCE(EXCLUDED.effective_at, change_events.effective_at),
    fail_closed          = EXCLUDED.fail_closed,
    migration            = EXCLUDED.migration,
    notice_id            = COALESCE(EXCLUDED.notice_id, change_events.notice_id),
    notice_sha256        = EXCLUDED.notice_sha256,
    provenance           = EXCLUDED.provenance,
    rationale            = EXCLUDED.rationale,
    normalizer_version   = EXCLUDED.normalizer_version,
    normalized_at        = now(),
    -- The provider's own words survive a re-read. Only fill it when the row
    -- has none, which happens when the agent saw the notice before any
    -- deterministic ingest did.
    summary              = CASE
        WHEN change_events.summary = '' THEN EXCLUDED.summary
        ELSE change_events.summary
    END
RETURNING id
"""

_UPSERT_IDENTIFIER_SQL: Final[str] = """
INSERT INTO change_event_identifiers (
    change_event_id, identifier, role, replacement, semantic, asserted_by
)
VALUES ($1, $2, $3::identifier_role, $4, $5, $6::change_provenance)
ON CONFLICT (change_event_id, identifier, role) DO UPDATE
SET replacement = EXCLUDED.replacement,
    semantic    = EXCLUDED.semantic,
    asserted_by = EXCLUDED.asserted_by
"""

# Corroboration is recorded, not enforced. The pull request is where risk is
# held, so a live check that agrees is evidence a card can show rather than a
# gate a migration has to pass.
_CORROBORATE_SQL: Final[str] = """
UPDATE change_event_identifiers i
SET corroborated_by = 'live'::change_provenance,
    live_status     = p.status,
    observed_at     = p.checked_at
FROM identifier_liveness p
WHERE p.identifier = i.identifier
  AND p.status = 'not_found'
  AND i.role = 'retired'
  AND i.change_event_id = $1
"""

# Identifiers the notice named that are no longer in it. A corrected notice
# that drops a model must not leave the old row joining against customer code.
_PRUNE_SQL: Final[str] = """
DELETE FROM change_event_identifiers
WHERE change_event_id = $1 AND identifier <> ALL($2::text[])
"""


@dataclass(frozen=True, slots=True)
class CorpusWrite:
    """What one normalization changed."""

    change_event_id: str
    external_id: str
    identifiers: int


def change_kind_for(change_type: str) -> str:
    return _CHANGE_KIND_BY_TYPE.get(change_type, "change")


def retires(change_type: str) -> bool:
    """Whether identifiers named by this kind of notice stop working as written."""
    return change_type not in _NON_RETIRING_CHANGE_TYPES


def _replacements_json(manifest: ChangeManifest) -> list[dict[str, str]]:
    """The flat replacement list the existing read path still renders."""
    rows: list[dict[str, str]] = []
    for identifier in manifest.affected_identifiers:
        replacement, semantic = manifest.replacement_for(identifier)
        if not replacement:
            continue
        rows.append(
            {
                "from": identifier,
                "to": replacement,
                "notes": "semantic" if semantic else "mechanical",
            }
        )
    return rows


async def write_manifest(
    connection: asyncpg.Connection,
    manifest: ChangeManifest,
    *,
    product: str = "",
    title: str = "",
    summary: str = "",
    rationale: str = "",
    notice_id: str | None = None,
    notice_sha256: str = "",
    provenance: str = AGENT,
) -> CorpusWrite:
    """Persist one normalized notice and the identifiers it names.

    Idempotent on (provider, change_id): reading the same notice twice corrects
    the row rather than producing a second card saying the same thing.
    """
    change_type = str(manifest.change_type)
    identifier_role = "retired" if retires(change_type) else "mentioned"

    row = await connection.fetchrow(
        _UPSERT_EVENT_SQL,
        manifest.change_id,
        manifest.provider,
        product,
        change_kind_for(change_type),
        str(manifest.severity),
        title or manifest.change_id,
        summary,
        [str(url) for url in manifest.source_urls],
        list(manifest.affected_identifiers),
        _replacements_json(manifest),
        manifest.announced_at,
        manifest.effective_at,
        not manifest.has_verifiable_evidence,
        "semantic" if manifest.semantic_migration_required else "mechanical",
        notice_id,
        notice_sha256,
        provenance,
        rationale.strip()[:MAX_RATIONALE_CHARS],
        NORMALIZER_VERSION,
    )
    if row is None:  # pragma: no cover - upsert always returns
        raise RuntimeError(f"could not write corpus row for {manifest.change_id}")
    event_id = row["id"]

    for identifier in manifest.affected_identifiers:
        replacement, semantic = manifest.replacement_for(identifier)
        await connection.execute(
            _UPSERT_IDENTIFIER_SQL,
            event_id,
            identifier,
            identifier_role,
            replacement,
            semantic,
            provenance,
        )

    if manifest.recommended_replacement:
        await connection.execute(
            _UPSERT_IDENTIFIER_SQL,
            event_id,
            manifest.recommended_replacement,
            "replacement",
            None,
            False,
            provenance,
        )

    keep = list(manifest.affected_identifiers)
    if manifest.recommended_replacement:
        keep.append(manifest.recommended_replacement)
    await connection.execute(_PRUNE_SQL, event_id, keep)
    await connection.execute(_CORROBORATE_SQL, event_id)

    log.info(
        "normalized %s into the corpus (%d identifiers)",
        manifest.change_id,
        len(manifest.affected_identifiers),
    )
    return CorpusWrite(
        change_event_id=str(event_id),
        external_id=manifest.change_id,
        identifiers=len(manifest.affected_identifiers),
    )


async def write_manifest_payload(
    connection: asyncpg.Connection, payload: dict[str, Any], **kwargs: Any
) -> CorpusWrite:
    """Validate a recorded manifest, then persist it."""
    return await write_manifest(connection, ChangeManifest.model_validate(payload), **kwargs)


__all__ = [
    "AGENT",
    "MAX_RATIONALE_CHARS",
    "NORMALIZER_VERSION",
    "CorpusWrite",
    "change_kind_for",
    "retires",
    "write_manifest",
    "write_manifest_payload",
]
