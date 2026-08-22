"""Official Google notes that the Releases tab is allowed to materialize.

The indexer names every Gemini / Imagen / Veo identifier a project uses, and
every Google API host it calls. This module turns those into `change_events` by
intersecting them with:

* the pinned demo watchlist
* the committed Google models lifecycle catalog
* ingested `provider_change_notes` whose text names a used identifier, or whose
  product is a service the project calls and whose kind is breaking

The last clause is what lets a whole-service shutdown land. Such a notice names
a product and no model at all, so a model-only join read every one of them as
unrelated to every project.

Nothing here invents a deprecation. A catalog row or a release note that names
nothing this project uses is left out, so the inbox stays a join against
inventory rather than a dump of every Google retirement.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from packages.providers.google.probe import is_service_identifier
from packages.state.findings import (
    BREAKING_KINDS,
    canonical_identifier,
    identifier_aliases,
)
from packages.state.google_models import CatalogUnavailableError, ModelChange, load_google_models
from packages.state.watchlist import WatchlistNote

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

CHANGE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "deprecation",
        "replacement",
        "new_identifier",
        "breaking_change",
        "feature",
        "fix",
        "issue",
        "security",
        "announcement",
        "change",
        "libraries",
        "other",
    }
)

# Short tokens like "gemini" or "imagen" are not identifiers.
_MIN_IDENTIFIER_CHARS: Final[int] = 8

_UNDEFINED_TABLE: Final[str] = "42P01"

# A model id, or the API host a call goes to. The host arm is what lets a
# whole-service deprecation reach the inbox: "Dialogflow ES is shut down" names
# no model, so a model-only pattern read it as unrelated to every project.
_NOTE_IDENTIFIER: Final[re.Pattern[str]] = re.compile(
    r"(?:models/|vertex/)?(?:imagen|gemini|veo)-\d[\w.-]*"
    r"|[a-z0-9][a-z0-9-]*\.googleapis\.com",
    re.IGNORECASE,
)


def expand_usage_set(identifiers: Iterable[str]) -> set[str]:
    """Every alias that should count as the same inventory hit."""
    expanded: set[str] = set()
    for item in identifiers:
        value = item.strip()
        if not value:
            continue
        expanded.update(identifier_aliases(value))
        expanded.add(canonical_identifier(value))
    return expanded


def identifier_is_covered(identifier: str, covered: set[str]) -> bool:
    """True when a note already names this model (or an alias of it)."""
    return bool(expand_usage_set([identifier]) & covered)


def product_for_identifier(identifier: str) -> str:
    """Family label for an inbox card. Not a routing decision."""
    lowered = canonical_identifier(identifier).lower()
    if is_service_identifier(lowered):
        return lowered
    if lowered.startswith("imagen-") or "/imagen-" in lowered:
        return "Imagen"
    if lowered.startswith("veo-") or "/veo-" in lowered:
        return "Veo"
    if lowered.startswith("gemini-") or "/gemini-" in lowered:
        return "Gemini"
    return "Google"


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def catalog_notes_for_usages(
    changes: Sequence[ModelChange],
    usage_identifiers: Iterable[str],
    covered_identifiers: Iterable[str],
    *,
    today: date | None = None,
) -> tuple[WatchlistNote, ...]:
    """Lifecycle rows that name a used identifier nobody has pinned yet."""
    usages = expand_usage_set(usage_identifiers)
    covered = expand_usage_set(covered_identifiers)
    if not usages:
        return ()
    day = today or date.today()
    notes: list[WatchlistNote] = []
    seen: set[str] = set()
    for change in changes:
        retired = [item.strip() for item in change.retired_identifiers if item.strip()]
        if not retired:
            continue
        overlap = [item for item in retired if expand_usage_set([item]) & usages]
        if not overlap:
            continue
        if any(identifier_is_covered(item, covered) for item in overlap):
            continue
        external_id = f"catalog:{change.id}"
        if external_id in seen:
            continue
        seen.add(external_id)
        replacement = (change.recommended_replacement or "").strip() or None
        effective = _as_date(change.effective_at)
        announced = _as_date(change.published_at)
        already_broken = effective is not None and effective <= day
        kind = change.kind if change.kind in CHANGE_KINDS else "deprecation"
        replacements = (
            [{"from": overlap[0], "to": replacement, "notes": "catalog"}]
            if replacement
            else []
        )
        notes.append(
            {
                "external_id": external_id,
                "provider": "google",
                "product": product_for_identifier(overlap[0]),
                "change_kind": kind,
                "severity": "high" if already_broken and kind in BREAKING_KINDS else "medium",
                "title": change.title,
                "summary": (
                    f"{overlap[0]} is listed on the official Google model lifecycle. "
                    + (
                        f"Replacement named by the catalog: {replacement}."
                        if replacement
                        else "The catalog does not name a replacement."
                    )
                ),
                "source_urls": [change.source_url] if change.source_url else [],
                "identifiers": overlap,
                "replacements": replacements,
                "announced_at": announced.isoformat() if announced else None,
                "effective_at": effective.isoformat() if effective else None,
                "fail_closed": already_broken and replacement is None and kind in BREAKING_KINDS,
                "false_positive": False,
                "migration": None,
            }
        )
    return tuple(notes)


def note_identifiers_in_text(text: str, usage_identifiers: Iterable[str]) -> list[str]:
    """Used identifiers that appear in official release-note prose."""
    usages = expand_usage_set(usage_identifiers)
    if not usages or not text:
        return []
    haystack = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    extracted = {canonical_identifier(match.group(0)) for match in _NOTE_IDENTIFIER.finditer(text)}
    for ident in sorted(usages, key=len, reverse=True):
        canon = canonical_identifier(ident)
        if len(canon) < _MIN_IDENTIFIER_CHARS:
            continue
        if canon in seen:
            continue
        if canon.lower() in haystack or canon in extracted or ident.lower() in haystack:
            seen.add(canon)
            found.append(canon)
    return found


def service_identifiers_for_note(
    product: str,
    kind: str,
    hosts_by_product: Mapping[str, tuple[str, ...]],
    usage_identifiers: Iterable[str],
) -> list[str]:
    """API hosts this project calls that belong to the note's product.

    A whole-service shutdown names the product ("Dialogflow"), never a host and
    never a model, so text matching finds nothing to join on. The catalog knows
    which host answers for that product and the index knows whether the tree
    calls it; this is the join between the two.

    Restricted to breaking kinds on purpose. Matching a product is far coarser
    than matching a model id — every feature note for Vertex AI would otherwise
    become a card for every project that calls `aiplatform.googleapis.com`.
    """
    if kind not in BREAKING_KINDS:
        return []
    hosts = hosts_by_product.get(product.strip().lower())
    if not hosts:
        return []
    usages = expand_usage_set(usage_identifiers)
    return [host for host in hosts if host in usages]


def release_note_event(
    *,
    external_id: str,
    product: str,
    kind: str,
    title: str,
    summary: str,
    source_url: str,
    published_at: str | None,
    identifiers: Sequence[str],
    covered_identifiers: Iterable[str],
) -> WatchlistNote | None:
    """One ingested release note, or None when the identifiers are already pinned."""
    cleaned = [item.strip() for item in identifiers if item.strip()]
    if not cleaned:
        return None
    covered = expand_usage_set(covered_identifiers)
    if any(identifier_is_covered(item, covered) for item in cleaned):
        return None
    mapped = kind if kind in CHANGE_KINDS else "other"
    published = _as_date(published_at)
    return {
        "external_id": f"note:{external_id}",
        "provider": "google",
        "product": product or product_for_identifier(cleaned[0]),
        "change_kind": mapped,
        "severity": "high" if mapped in BREAKING_KINDS else "medium",
        "title": title[:140],
        "summary": summary[:400],
        "source_urls": [source_url] if source_url else [],
        "identifiers": list(cleaned),
        "replacements": [],
        "announced_at": published.isoformat() if published else None,
        "effective_at": published.isoformat() if published and mapped in BREAKING_KINDS else None,
        "fail_closed": mapped in BREAKING_KINDS,
        "false_positive": False,
        "migration": None,
    }


def manifest_event(payload: Mapping[str, Any]) -> WatchlistNote | None:
    """Turn a recorded ChangeManifest into a watchlist-shaped note.

    Refuses a payload that names no identifier or no official source URL.
    """
    change_id = str(payload.get("change_id") or "").strip()
    identifiers = [
        str(item).strip()
        for item in (payload.get("affected_identifiers") or [])
        if str(item).strip()
    ]
    urls = [str(item).strip() for item in (payload.get("source_urls") or []) if str(item).strip()]
    if not change_id or not identifiers or not urls:
        return None
    replacement = str(payload.get("recommended_replacement") or "").strip() or None
    effective = _as_date(str(payload.get("effective_at") or "") or None)
    announced = _as_date(str(payload.get("announced_at") or "") or None)
    semantic = bool(payload.get("semantic_migration_required"))
    change_type = str(payload.get("change_type") or "deprecation")
    kind = "deprecation" if "retir" in change_type or change_type == "deprecation" else "other"
    if "breaking" in change_type:
        kind = "breaking_change"
    return {
        "external_id": change_id,
        "provider": str(payload.get("provider") or "google"),
        "product": product_for_identifier(identifiers[0]),
        "change_kind": kind,
        "severity": str(payload.get("severity") or "high"),
        "title": str(payload.get("title") or change_id),
        "summary": str(payload.get("rationale") or payload.get("summary") or change_id)[:400],
        "source_urls": urls,
        "identifiers": identifiers,
        "replacements": (
            [{"from": identifiers[0], "to": replacement, "notes": "manifest"}]
            if replacement
            else []
        ),
        "announced_at": announced.isoformat() if announced else None,
        "effective_at": effective.isoformat() if effective else None,
        "fail_closed": replacement is None,
        "false_positive": False,
        "migration": "semantic" if semantic else "mechanical",
    }


_USAGE_IDENTIFIERS_SQL: Final[str] = """
SELECT DISTINCT u.identifier
FROM project_provider_usages u
WHERE u.project_id = $1 AND u.provider = $2
"""

_COVERED_IDENTIFIERS_SQL: Final[str] = """
SELECT DISTINCT ON (external_id) affected_identifiers
FROM change_events
WHERE provider = $1
ORDER BY external_id, detected_at DESC
"""

_NOTES_SQL: Final[str] = """
SELECT n.external_id, n.product, n.kind, n.title, n.summary,
       n.source_url, n.published_at
FROM provider_change_notes n
JOIN providers p ON p.id = n.provider_id AND p.retired_at IS NULL
WHERE p.slug = $1
"""

_SERVICE_HOSTS_SQL: Final[str] = """
SELECT s.product, s.identifiers
FROM provider_services s
JOIN providers p ON p.id = s.provider_id AND p.retired_at IS NULL
WHERE p.slug = $1 AND s.retired_at IS NULL
"""


async def project_usage_identifiers(
    connection: asyncpg.Connection, project_id: UUID, provider: str
) -> set[str]:
    """Identifiers the indexer stored for this project."""
    rows = await connection.fetch(_USAGE_IDENTIFIERS_SQL, project_id, provider)
    return {str(row["identifier"]) for row in rows if row["identifier"]}


async def service_hosts_by_product(
    connection: asyncpg.Connection, provider: str
) -> dict[str, tuple[str, ...]]:
    """Product name to the API hosts it answers on, from the ingested catalog.

    Empty when nobody has connected a catalog, which is the honest answer: with
    no catalog there is nothing that maps "Dialogflow" to a hostname, and a
    guess would put a shutdown notice in front of a project that never called it.
    """
    try:
        rows = await connection.fetch(_SERVICE_HOSTS_SQL, provider)
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == _UNDEFINED_TABLE:
            return {}
        raise
    mapping: dict[str, list[str]] = {}
    for row in rows:
        key = str(row["product"] or "").strip().lower()
        if not key:
            continue
        bucket = mapping.setdefault(key, [])
        for host in row["identifiers"] or ():
            value = str(host).strip()
            if value and value not in bucket:
                bucket.append(value)
    return {key: tuple(values) for key, values in mapping.items() if values}


async def covered_identifiers(connection: asyncpg.Connection, provider: str) -> set[str]:
    """Identifiers already named on a latest `change_events` row."""
    rows = await connection.fetch(_COVERED_IDENTIFIERS_SQL, provider)
    found: set[str] = set()
    for row in rows:
        found.update(item for item in (row["affected_identifiers"] or []) if item)
    return found


def _event_args(note: WatchlistNote) -> tuple[Any, ...]:
    return (
        note["external_id"],
        note["provider"],
        note["product"],
        note["change_kind"],
        note["severity"] if note["severity"] in {"low", "medium", "high", "critical"} else "medium",
        note["title"],
        note["summary"],
        note["source_urls"],
        note["identifiers"],
        note["replacements"],
        _as_date(note["announced_at"]),
        _as_date(note["effective_at"]),
        note["fail_closed"],
        note["false_positive"],
        note["migration"],
    )


async def _insert_notes(connection: asyncpg.Connection, notes: Sequence[WatchlistNote]) -> int:
    from packages.state.findings import _ENSURE_EVENT_SQL

    inserted = 0
    for note in notes:
        status = await connection.execute(_ENSURE_EVENT_SQL, *_event_args(note))
        if status.endswith("1"):
            inserted += 1
    return inserted


async def ensure_catalog_events(
    connection: asyncpg.Connection, provider: str, usage_identifiers: set[str]
) -> int:
    """Pin lifecycle rows that overlap this project's inventory."""
    if provider != "google" or not usage_identifiers:
        return 0
    try:
        snapshot = load_google_models()
    except CatalogUnavailableError as exc:
        log.warning("google models catalog unavailable; skip catalog inbox: %s", exc)
        return 0
    covered = await covered_identifiers(connection, provider)
    notes = catalog_notes_for_usages(snapshot.changes, usage_identifiers, covered)
    return await _insert_notes(connection, notes)


async def ensure_release_note_events(
    connection: asyncpg.Connection, provider: str, usage_identifiers: set[str]
) -> int:
    """Pin ingested release notes whose text names a used identifier."""
    if not usage_identifiers:
        return 0
    try:
        rows = await connection.fetch(_NOTES_SQL, provider)
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == _UNDEFINED_TABLE:
            return 0
        raise
    covered = await covered_identifiers(connection, provider)
    hosts_by_product = await service_hosts_by_product(connection, provider)
    notes: list[WatchlistNote] = []
    for row in rows:
        text = " ".join(
            str(row[key] or "") for key in ("product", "title", "summary")
        )
        kind = str(row["kind"] or "other")
        hits = note_identifiers_in_text(text, usage_identifiers)
        for host in service_identifiers_for_note(
            str(row["product"] or ""), kind, hosts_by_product, usage_identifiers
        ):
            if host not in hits:
                hits.append(host)
        event = release_note_event(
            external_id=str(row["external_id"]),
            product=str(row["product"] or ""),
            kind=str(row["kind"] or "other"),
            title=str(row["title"] or ""),
            summary=str(row["summary"] or ""),
            source_url=str(row["source_url"] or ""),
            published_at=str(row["published_at"] or "") or None,
            identifiers=hits,
            covered_identifiers=covered,
        )
        if event is None:
            continue
        covered.update(event["identifiers"])
        notes.append(event)
    return await _insert_notes(connection, notes)


async def ensure_inbox_corpus(
    connection: asyncpg.Connection, project_id: UUID, provider: str
) -> dict[str, int]:
    """Watchlist + official notes that this project's index can join."""
    from packages.state.findings import ensure_watchlist

    watchlist = await ensure_watchlist(connection, provider)
    usages = await project_usage_identifiers(connection, project_id, provider)
    catalog = await ensure_catalog_events(connection, provider, usages)
    notes = await ensure_release_note_events(connection, provider, usages)
    return {"watchlist": watchlist, "catalog": catalog, "notes": notes, "usages": len(usages)}


async def upsert_event_from_manifest(
    connection: asyncpg.Connection, payload: Mapping[str, Any]
) -> bool:
    """Persist a Change Intelligence manifest as a `change_events` row."""
    note = manifest_event(payload)
    if note is None:
        return False
    covered = await covered_identifiers(connection, note["provider"])
    if any(identifier_is_covered(item, covered) for item in note["identifiers"]):
        return False
    return (await _insert_notes(connection, [note])) == 1


__all__ = [
    "catalog_notes_for_usages",
    "covered_identifiers",
    "ensure_catalog_events",
    "ensure_inbox_corpus",
    "ensure_release_note_events",
    "expand_usage_set",
    "identifier_is_covered",
    "manifest_event",
    "note_identifiers_in_text",
    "product_for_identifier",
    "project_usage_identifiers",
    "release_note_event",
    "service_hosts_by_product",
    "service_identifiers_for_note",
    "upsert_event_from_manifest",
]
