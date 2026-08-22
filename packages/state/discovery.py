"""Find breaks nobody wrote a notice about, and record what Change Intelligence proves.

Two ways a release reaches the inbox, and until now neither of them ran.

*From a manifest.* Change Intelligence reads a notice, confirms it against the
deterministic parse, and records a `ChangeManifest`. `upsert_event_from_manifest`
turns that into a `change_events` row. The function existed with no caller, so
the Releases tab only ever showed the pinned watchlist.

*From a probe.* The indexer knows every model identifier the fleet actually
calls. The probe knows which of those a Google surface has stopped publishing.
An identifier in both sets that no `change_events` row covers is a break in
production that no notice describes — the case a watchlist can never catch,
because someone has to notice it first in order to type it in.

A discovered retirement is recorded honestly. There is no announcement to cite,
so the evidence is the listing call itself, the row carries no replacement, and
it fails closed (CLAUDE.md constraint 10). PatchAPI reports "this stopped
resolving and we found no notice", never an invented deprecation with an
invented successor.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from packages.providers.google.probe import (
    GEMINI_API,
    ProbeResult,
    ProbeStatus,
    probe_identifiers,
)
from packages.state.inbox_corpus import (
    covered_identifiers,
    identifier_is_covered,
    product_for_identifier,
)
from packages.state.watchlist import WatchlistNote

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

DEPRECATIONS_URL: Final[str] = "https://ai.google.dev/gemini-api/docs/deprecations"

_INDEXED_IDENTIFIERS_SQL: Final[str] = """
SELECT DISTINCT identifier FROM provider_usages WHERE provider = $1
"""

_SUBSCRIBED_PROJECTS_SQL: Final[str] = """
SELECT DISTINCT s.project_id
FROM project_provider_subscriptions s
JOIN providers p ON p.id = s.provider_id
WHERE p.slug = $1 AND p.retired_at IS NULL
"""


def discovery_event(result: ProbeResult) -> WatchlistNote:
    """A retirement observed on the wire, with no notice to cite.

    `fail_closed` is set and no replacement is named on purpose: the probe
    proves the model is gone, and proves nothing at all about what replaces it.
    """
    surface = "the Gemini API" if result.surface == GEMINI_API else "Vertex AI"
    return {
        "external_id": f"probe:{result.surface}:{result.identifier}",
        "provider": "google",
        "product": product_for_identifier(result.identifier),
        "change_kind": "breaking_change",
        "severity": "critical",
        "title": f"{result.identifier} no longer resolves",
        "summary": (
            f"{surface} no longer lists {result.identifier}, and no published notice "
            "covers it. Calls to this model fail now. PatchAPI found no announcement, "
            "so it names no replacement — a human has to choose one."
        ),
        "source_urls": [result.source_url or DEPRECATIONS_URL, DEPRECATIONS_URL],
        "identifiers": [result.identifier],
        "replacements": [],
        "announced_at": None,
        # Observed, not announced. The date is when we saw it, and the summary
        # says so, rather than implying the provider scheduled it for today.
        "effective_at": result.checked_at[:10],
        "fail_closed": True,
        "false_positive": False,
        "migration": None,
    }


async def indexed_identifiers(connection: asyncpg.Connection, provider: str) -> list[str]:
    """Every identifier the repo indexer has stored for `provider`."""
    rows = await connection.fetch(_INDEXED_IDENTIFIERS_SQL, provider)
    return [str(row["identifier"]) for row in rows]


async def undocumented_retirements(
    connection: asyncpg.Connection,
    *,
    provider: str = "google",
    results: tuple[ProbeResult, ...] | None = None,
) -> list[ProbeResult]:
    """Probed-gone identifiers that no existing change event mentions."""
    if results is None:
        identifiers = await indexed_identifiers(connection, provider)
        if not identifiers:
            return []
        results = await probe_identifiers(identifiers)
    covered = await covered_identifiers(connection, provider)
    return [
        result
        for result in results
        if result.status is ProbeStatus.NOT_FOUND
        and not identifier_is_covered(result.identifier, covered)
    ]


async def record_discovered_retirements(
    connection: asyncpg.Connection,
    *,
    provider: str = "google",
    results: tuple[ProbeResult, ...] | None = None,
) -> list[str]:
    """Write a change event for each undocumented break. Returns the external ids."""
    from packages.state.inbox_corpus import _insert_notes

    discovered = await undocumented_retirements(connection, provider=provider, results=results)
    written: list[str] = []
    for result in discovered:
        note = discovery_event(result)
        if await _insert_notes(connection, [note]) == 1:
            written.append(note["external_id"])
            log.info("recorded undocumented retirement %s", result.identifier)
    return written


async def record_manifest_release(connection: asyncpg.Connection, payload: dict[str, Any]) -> bool:
    """Persist a Change Intelligence manifest as a release, then reclassify."""
    from packages.state.inbox_corpus import upsert_event_from_manifest

    if not await upsert_event_from_manifest(connection, payload):
        return False
    await refresh_subscribed(connection, str(payload.get("provider") or "google"))
    return True


async def refresh_subscribed(connection: asyncpg.Connection, provider: str) -> int:
    """Reclassify every project subscribed to `provider`."""
    from packages.state.findings import refresh_project_findings

    rows = await connection.fetch(_SUBSCRIBED_PROJECTS_SQL, provider)
    for row in rows:
        await refresh_project_findings(connection, UUID(str(row["project_id"])), provider)
    return len(rows)


__all__ = [
    "DEPRECATIONS_URL",
    "discovery_event",
    "indexed_identifiers",
    "record_discovered_retirements",
    "record_manifest_release",
    "refresh_subscribed",
    "undocumented_retirements",
]
