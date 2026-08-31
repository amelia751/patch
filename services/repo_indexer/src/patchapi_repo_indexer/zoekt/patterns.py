"""Versioned provider regexes for the indexed Layer A query (repo-indexer.md §5.2).

The literal watchlist can only find model IDs somebody enumerated. These
patterns are why Layer A is an index and not a `grep`: they catch the members of
a family nobody wrote down, and the index answers them without re-reading the
tree.

Patterns are RE2-compatible so the same string can be sent to `zoekt-webserver`
and compiled locally to name the identifier a matched line actually contains.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Final

from packages.providers import registry
from packages.providers.errors import UnknownProviderError as RegistryUnknownProviderError
from patchapi_repo_indexer.config import DEFAULT_PROVIDER
from patchapi_repo_indexer.errors import UnknownProviderError

# Bumped whenever the *composition* of a query changes — how family patterns and
# manifest literals are combined. The patterns themselves are versioned by the
# descriptor that declares them, and `ProviderDescriptor.search_intent` is what
# a stored finding is traced to.
PATTERNS_VERSION: Final[str] = "2.0.0"


def _google_pattern(name: str) -> str:
    """One family regex from Google's descriptor, by the name it is declared under."""
    return registry.descriptor_for(DEFAULT_PROVIDER).pattern_named(name)


# Vertex-routed ids are a different inventory key than the bare model id.
# Declared first in the descriptor so a `vertex/imagen-…` line records the
# prefix, not the suffix.
GOOGLE_VERTEX_ROUTED: Final[str] = _google_pattern("vertex_routed")

# The GA Imagen family plus later members with the same shape.
GOOGLE_IMAGEN_FAMILY: Final[str] = _google_pattern("imagen_family")

# The retired preview identifier is its own finding in
# `demo/storygen/expected-findings.yaml`, not a variant of the GA one: it has its
# own replacement and its own deprecation date, so it gets its own pattern.
GOOGLE_IMAGEN_PREVIEW: Final[str] = _google_pattern("imagen_preview")

# Any Gemini generation id. The inbox join decides which of these are retired;
# the index only names what the tree contains.
GOOGLE_GEMINI_FAMILY: Final[str] = _google_pattern("gemini_family")

# Retired 2026-06-01. Kept as a tighter alias of GOOGLE_GEMINI_FAMILY so older
# tests and stored findings can still name the regex that produced them; the
# descriptor marks it `queried: false`, so it is not sent to the index.
GOOGLE_GEMINI20_FAMILY: Final[str] = _google_pattern("gemini_20_family")

# The service a call goes to, not the model it names. A shutdown announcement
# for `dialogflow.googleapis.com` names no model, so a model-only index has
# nothing for it to join against and the release note stays invisible. This is
# the inventory key that lets a whole-service deprecation find its call sites.
GOOGLE_SERVICE_HOST: Final[str] = _google_pattern("service_host")


def provider_patterns() -> Mapping[str, tuple[str, ...]]:
    """Every registered provider's queried family patterns, by slug.

    A live read of the registry: a descriptor loaded from Postgres widens what
    an index is asked for without a redeploy.
    """
    return {descriptor.provider_id: descriptor.patterns() for descriptor in registry.descriptors()}


def patterns_for(provider: str, identifiers: Sequence[str] | None = None) -> tuple[str, ...]:
    """Return the regexes to query the index with for `provider`.

    The provider's family patterns come first; any supplied identifier that no
    family pattern already covers is appended as an escaped literal. A manifest
    naming an identifier outside the known families must still be searched for —
    dropping it would report an affected repository as clean.

    Fails closed on an unregistered provider for the same reason `watchlist_for`
    does: an empty pattern set finds nothing and looks exactly like good news.
    """
    try:
        family = registry.descriptor_for(provider).patterns()
    except RegistryUnknownProviderError as exc:
        raise UnknownProviderError(str(exc)) from exc

    if not identifiers:
        return family

    compiled = compile_patterns(family)
    extra: list[str] = []
    for identifier in identifiers:
        value = identifier.strip()
        if not value or any(pattern.search(value) for pattern in compiled):
            continue
        literal = re.escape(value)
        if literal not in extra:
            extra.append(literal)
    return family + tuple(extra)


def compile_patterns(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    """Compile `patterns` case-sensitively.

    Case matters: a model ID is an exact string, and a case-insensitive match
    would put prose like "Imagen" in front of a reviewer as a call site.
    """
    return tuple(re.compile(pattern) for pattern in patterns)


def match_identifiers(line: str, patterns: Sequence[re.Pattern[str]]) -> tuple[str, ...]:
    """Return the concrete identifiers `patterns` find in `line`, left to right.

    A match nested inside a longer one is dropped: `imagen-4.0-generate-001`
    found by the family pattern and a shorter prefix found by another are one
    finding, and reporting both would double-count a single call site.
    """
    spans = [
        (match.start(), match.end(), match.group(0))
        for pattern in patterns
        for match in pattern.finditer(line)
    ]
    # Longest match at a given offset first, so a shorter match inside it is
    # recognised as contained rather than kept alongside it.
    spans.sort(key=lambda span: (span[0], -span[1]))

    kept: list[tuple[int, int]] = []
    found: list[str] = []
    for start, end, text in spans:
        if any(outer_start <= start and end <= outer_end for outer_start, outer_end in kept):
            continue
        kept.append((start, end))
        if text not in found:
            found.append(text)
    return tuple(found)


__all__ = [
    "GOOGLE_GEMINI20_FAMILY",
    "GOOGLE_GEMINI_FAMILY",
    "GOOGLE_IMAGEN_FAMILY",
    "GOOGLE_IMAGEN_PREVIEW",
    "GOOGLE_SERVICE_HOST",
    "GOOGLE_VERTEX_ROUTED",
    "PATTERNS_VERSION",
    "compile_patterns",
    "match_identifiers",
    "patterns_for",
    "provider_patterns",
]
