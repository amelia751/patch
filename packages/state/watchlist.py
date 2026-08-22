"""Pinned Google demo notes that Subscribe always materializes.

These are the product-rule cards (Imagen retirement, preview-id claim,
Vertex prefix leftover, fal-ai false positive, Spanish “imagen”). Official
catalog rows and ingested release notes that name a used identifier are
added beside this set by `inbox_corpus`. This file stays a closed demo
corpus — it does not invent a deprecation from a live HTML crawl.

Every summary here describes the change, never a project. One row is shown to
every subscriber, so a sentence like "no usages in this project" is false for
the next reader and contradicts the inventory rendered beside it. Which repos
are affected is counted deterministically per project and displayed already.
"""

from __future__ import annotations

from typing import Final, TypedDict


class WatchlistNote(TypedDict):
    external_id: str
    provider: str
    product: str
    change_kind: str
    severity: str
    title: str
    summary: str
    source_urls: list[str]
    identifiers: list[str]
    replacements: list[dict[str, str]]
    announced_at: str | None
    effective_at: str | None
    fail_closed: bool
    false_positive: bool
    migration: str | None


GOOGLE_PROVIDER: Final[str] = "google"

GOOGLE_WATCHLIST: Final[tuple[WatchlistNote, ...]] = (
    {
        "external_id": "imagen4-retirement-2026-08-17",
        "provider": GOOGLE_PROVIDER,
        "product": "Imagen",
        "change_kind": "deprecation",
        "severity": "high",
        "title": "Imagen 4 retirement",
        "summary": (
            "Imagen 4 generate models stop resolving. Gemini native image "
            "generation is a different request surface, not a string rewrite."
        ),
        "source_urls": [
            "https://ai.google.dev/gemini-api/docs/deprecations",
            "https://ai.google.dev/gemini-api/docs/changelog",
            "https://ai.google.dev/gemini-api/docs/models/imagen",
        ],
        "identifiers": [
            "imagen-4.0-generate-001",
            "imagen-4.0-ultra-generate-001",
            "imagen-4.0-fast-generate-001",
        ],
        "replacements": [
            {
                "from": "imagen-4.0-generate-001",
                "to": "gemini-3.1-flash-image",
                "notes": "semantic",
            }
        ],
        "announced_at": "2026-06-24",
        "effective_at": "2026-08-17",
        "fail_closed": False,
        "false_positive": False,
        "migration": "semantic",
    },
    {
        "external_id": "gemini20-flash-shutdown-2026-06-01",
        "provider": GOOGLE_PROVIDER,
        "product": "Gemini",
        "change_kind": "deprecation",
        "severity": "high",
        "title": "Gemini 2.0 Flash shutdown",
        "summary": (
            "The gemini-2.0-flash identifiers stop being served. Each has a "
            "direct 3.5 equivalent, so the move is a string rewrite rather "
            "than a change of request surface."
        ),
        "source_urls": [
            "https://ai.google.dev/gemini-api/docs/deprecations",
            "https://ai.google.dev/gemini-api/docs/changelog",
        ],
        "identifiers": [
            "gemini-2.0-flash",
            "gemini-2.0-flash-001",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash-lite-001",
        ],
        "replacements": [
            {
                "from": "gemini-2.0-flash",
                "to": "gemini-3.5-flash",
                "notes": "mechanical",
            }
        ],
        "announced_at": None,
        "effective_at": "2026-06-01",
        "fail_closed": False,
        "false_positive": False,
        "migration": "mechanical",
    },
    {
        "external_id": "chg_flash_image_preview",
        "provider": GOOGLE_PROVIDER,
        "product": "Gemini",
        "change_kind": "replacement",
        "severity": "medium",
        "title": "gemini-3.1-flash-image-preview no longer resolves",
        "summary": (
            "The preview id stops resolving in favour of the stable one. The "
            "provider's replacement is a claim — the installed SDK has to "
            "resolve it before a patch writes it."
        ),
        "source_urls": ["https://ai.google.dev/gemini-api/docs/changelog"],
        "identifiers": ["gemini-3.1-flash-image-preview"],
        "replacements": [
            {
                "from": "gemini-3.1-flash-image-preview",
                "to": "gemini-3.1-flash-image",
                "notes": "claim — SDK must resolve",
            }
        ],
        "announced_at": None,
        "effective_at": "2026-07-17",
        "fail_closed": False,
        "false_positive": False,
        "migration": "mechanical",
    },
    {
        "external_id": "chg_flash_35_ga",
        "provider": GOOGLE_PROVIDER,
        "product": "Gemini",
        "change_kind": "new_identifier",
        "severity": "low",
        "title": "Gemini 3.5 Flash generally available",
        "summary": (
            "A new identifier on the generateContent surface. Nothing is "
            "retired by it, so adopting it is a choice rather than a repair."
        ),
        "source_urls": ["https://ai.google.dev/gemini-api/docs/models"],
        "identifiers": ["gemini-3.5-flash"],
        "replacements": [
            {
                "from": "gemini-3.5-flash",
                "to": "gemini-3.5-flash",
                "notes": "already current",
            }
        ],
        "announced_at": None,
        "effective_at": "2026-08-12",
        "fail_closed": False,
        "false_positive": False,
        "migration": None,
    },
    {
        "external_id": "adv-fal-ai-not-covered",
        "provider": GOOGLE_PROVIDER,
        "product": "Imagen",
        "change_kind": "other",
        "severity": "low",
        "title": "fal-ai/imagen4/preview is not this retirement",
        "summary": (
            "A third-party fal.ai-hosted model whose id contains imagen4. "
            "Not a Google first-party endpoint. Editing it is an unnecessary change."
        ),
        "source_urls": [],
        "identifiers": ["fal-ai/imagen4/preview"],
        "replacements": [],
        "announced_at": None,
        "effective_at": None,
        "fail_closed": False,
        "false_positive": True,
        "migration": None,
    },
    {
        "external_id": "adv-spanish-imagen-prose",
        "provider": GOOGLE_PROVIDER,
        "product": "Imagen",
        "change_kind": "other",
        "severity": "low",
        "title": "Spanish “imagen” is not an API identifier",
        "summary": (
            "Substring match on the Spanish word for image. Correct result "
            "is no finding and no run."
        ),
        "source_urls": [],
        "identifiers": [],
        "replacements": [],
        "announced_at": None,
        "effective_at": None,
        "fail_closed": False,
        "false_positive": False,
        "migration": None,
    },
    {
        "external_id": "ui-vertex-prefix-leftover",
        "provider": GOOGLE_PROVIDER,
        "product": "Vertex AI",
        "change_kind": "breaking_change",
        "severity": "high",
        "title": "Vertex-routed Imagen 4 left after a bare-id rewrite",
        "summary": (
            "The vertex/ prefix is a routing decision, not a different model. "
            "A migration that only rewrites bare ids leaves Vertex callers broken."
        ),
        "source_urls": ["https://ai.google.dev/gemini-api/docs/deprecations"],
        "identifiers": [
            "vertex/imagen-4.0-generate-001",
            "vertex/imagen-4.0-ultra-generate-001",
            "vertex/imagen-4.0-fast-generate-001",
        ],
        "replacements": [],
        "announced_at": None,
        "effective_at": "2026-08-17",
        "fail_closed": True,
        "false_positive": False,
        "migration": "semantic",
    },
)


def watchlist_for(provider: str) -> tuple[WatchlistNote, ...]:
    """Notes this Subscribe backfill is allowed to materialize."""
    return tuple(note for note in GOOGLE_WATCHLIST if note["provider"] == provider)


def replacement_id(note: WatchlistNote) -> str | None:
    """First `to` value, or None when the note fails closed."""
    if note["fail_closed"] or not note["replacements"]:
        return None
    target = (note["replacements"][0].get("to") or "").strip()
    return target or None


__all__ = [
    "GOOGLE_PROVIDER",
    "GOOGLE_WATCHLIST",
    "WatchlistNote",
    "replacement_id",
    "watchlist_for",
]
