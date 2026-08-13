"""Zoekt query client (repo-indexer.md §5.2).

Talks to `zoekt-webserver` over its JSON API. Every query is scoped to an
explicit shard set rather than filtered after the fact: an unscoped query that
is narrowed late is one forgotten condition away from showing one project
another project's files.

Any failure to reach or parse the webserver is `ZoektUnavailableError`. This
module never returns an empty list to mean "the index was not there", because
that is indistinguishable from "this repository is not affected".
"""

import base64
import binascii
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

import httpx

from patchapi_repo_indexer.config import ZOEKT_WEBSERVER_URL
from patchapi_repo_indexer.errors import ZoektUnavailableError
from patchapi_repo_indexer.zoekt.shard import ShardRef

log = logging.getLogger(__name__)

SEARCH_PATH: Final[str] = "/api/search"
LIST_PATH: Final[str] = "/api/list"

# The webserver memory-maps its shards and answers from RAM; a query that takes
# longer than this is a server in trouble, and waiting on it costs more than
# degrading to the literal walk.
QUERY_TIMEOUT_SECONDS: Final[float] = 30.0

DEFAULT_MAX_RESULTS: Final[int] = 1000

# RE2 metacharacters. Escaping only these keeps the produced pattern valid for
# both RE2 (the server) and Python's `re` (local identifier extraction).
_RE2_METACHARACTERS: Final[re.Pattern[str]] = re.compile(r"([.^$*+?()\[\]{}|\\])")


@dataclass(frozen=True, slots=True)
class ZoektMatch:
    """One matching line in one indexed file."""

    repository: str
    branch: str | None
    path: str
    line_number: int
    line: str
    matched_text: str


def _escape_re2(value: str) -> str:
    return _RE2_METACHARACTERS.sub(r"\\\1", value)


def _decode(value: Any) -> str:
    """Decode a Go `[]byte` field, which JSON carries as base64.

    Falls back to the raw string: some builds return plain text, and a line the
    client cannot decode must not silently become an empty excerpt.
    """
    if not isinstance(value, str):
        return ""
    try:
        return base64.b64decode(value, validate=True).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return value


def build_query(patterns: Sequence[str], shards: Sequence[ShardRef]) -> str:
    """Return the zoekt query for `patterns` restricted to `shards`.

    Repository scoping is anchored (`^name$`) so `acme/api` cannot also match
    `acme/api-internal`. Branch is not a query term: one shard directory holds
    one `(repository, branch)`, and a tree indexed without refs carries no
    branch metadata at all, so filtering on it in the query would turn "indexed
    without refs" into "not affected". `search_shards` narrows by branch on the
    way out instead, where a file with no branch metadata can be kept.
    """
    if not patterns:
        raise ValueError("a zoekt query needs at least one pattern")
    if not shards:
        raise ValueError("a zoekt query must name the shards it may read")

    alternation = "|".join(patterns)
    repositories = " or ".join(f"repo:^{_escape_re2(shard.repository)}$" for shard in shards)
    # A lone `repo:` atom must not be parenthesised. Zoekt reads `(repo:^x$)` as
    # a group holding nothing searchable and answers it with zero hits and no
    # error, which is the same reply an unaffected repository gives. The
    # parentheses are only needed to bind the `or` when there are several.
    scope = f"({repositories})" if len(shards) > 1 else repositories
    return f"case:yes {scope} ({alternation})"


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = ZOEKT_WEBSERVER_URL.rstrip("/") + path
    try:
        response = httpx.post(url, json=payload, timeout=QUERY_TIMEOUT_SECONDS)
        response.raise_for_status()
        document = response.json()
    except httpx.HTTPError as exc:
        raise ZoektUnavailableError(f"zoekt-webserver at {url} is unreachable: {exc}") from exc
    except ValueError as exc:
        raise ZoektUnavailableError(f"zoekt-webserver at {url} returned non-JSON") from exc

    if not isinstance(document, dict):
        raise ZoektUnavailableError(f"zoekt-webserver at {url} returned an unexpected document")
    return document


def _line_matches(
    repository: str, branch: str | None, path: str, file_entry: Any
) -> list[ZoektMatch]:
    matches: list[ZoektMatch] = []
    for entry in file_entry.get("LineMatches") or ():
        if not isinstance(entry, dict):
            continue
        line = _decode(entry.get("Line"))
        line_number = entry.get("LineNumber")
        if not isinstance(line_number, int) or line_number < 1:
            continue
        fragments = entry.get("LineFragments") or ()
        if not fragments:
            matches.append(ZoektMatch(repository, branch, path, line_number, line, line.strip()))
            continue
        for fragment in fragments:
            if not isinstance(fragment, dict):
                continue
            offset = fragment.get("LineOffset", 0)
            length = fragment.get("MatchLength", 0)
            text = line[offset : offset + length] if isinstance(offset, int) else ""
            matches.append(ZoektMatch(repository, branch, path, line_number, line, text))
    return matches


def _chunk_matches(
    repository: str, branch: str | None, path: str, file_entry: Any
) -> list[ZoektMatch]:
    """Parse the newer chunk-shaped response.

    Newer zoekt builds return `ChunkMatches` instead of `LineMatches`. Reading
    only the older shape against a newer server would report every repository as
    clean, which is the one answer this component may never invent.
    """
    matches: list[ZoektMatch] = []
    for chunk in file_entry.get("ChunkMatches") or ():
        if not isinstance(chunk, dict):
            continue
        content = _decode(chunk.get("Content")).splitlines()
        start = chunk.get("ContentStart") or {}
        first_line = start.get("LineNumber", 1)
        if not isinstance(first_line, int):
            continue
        for span in chunk.get("Ranges") or ():
            if not isinstance(span, dict):
                continue
            span_start = span.get("Start") or {}
            span_end = span.get("End") or {}
            line_number = span_start.get("LineNumber")
            if not isinstance(line_number, int) or line_number < 1:
                continue
            offset = line_number - first_line
            line = content[offset] if 0 <= offset < len(content) else ""
            if span_end.get("LineNumber") == line_number:
                # Columns are 1-based.
                text = line[span_start.get("Column", 1) - 1 : span_end.get("Column", 1) - 1]
            else:
                text = line.strip()
            matches.append(ZoektMatch(repository, branch, path, line_number, line, text))
    return matches


def _parse(document: dict[str, Any], max_results: int) -> list[ZoektMatch]:
    result = document.get("Result")
    if not isinstance(result, dict):
        raise ZoektUnavailableError("zoekt-webserver response carried no Result")

    matches: list[ZoektMatch] = []
    for file_entry in result.get("Files") or ():
        if not isinstance(file_entry, dict):
            continue
        path = file_entry.get("FileName")
        repository = file_entry.get("Repository")
        if not isinstance(path, str) or not isinstance(repository, str):
            continue
        branches = file_entry.get("Branches") or ()
        branch = branches[0] if branches and isinstance(branches[0], str) else None
        matches.extend(_line_matches(repository, branch, path, file_entry))
        matches.extend(_chunk_matches(repository, branch, path, file_entry))

    if len(matches) >= max_results:
        # A silently truncated result reads as "that is all there is". Say so.
        log.warning(
            "zoekt result truncated at max_results=%d; the inventory is incomplete", max_results
        )
    return matches


def search(
    pattern: str,
    *,
    repository: str | None = None,
    branch: str | None = None,
    regex: bool = True,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[ZoektMatch]:
    """Search one repository for one pattern.

    `repository` is keyword-optional in the signature and required in fact: an
    unscoped query would read every shard the webserver serves, which is every
    tenant. A fleet-wide question is `search_shards` over the shards the caller
    is entitled to.

    `regex=False` searches for `pattern` literally; the pattern is escaped here
    rather than by the caller so a model ID containing a `.` cannot become a
    wildcard by accident.
    """
    if repository is None:
        raise ValueError(
            "search requires a repository; use search_shards for a multi-repository query"
        )
    expression = pattern if regex else _escape_re2(pattern)
    return search_shards(
        [expression],
        [ShardRef(repository=repository, branch=branch or "main")],
        max_results=max_results,
    )


def search_shards(
    patterns: Sequence[str],
    shards: Sequence[ShardRef],
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[ZoektMatch]:
    """Search `patterns` across exactly the shards the caller is entitled to."""
    query = build_query(patterns, shards)
    document = _post(
        SEARCH_PATH,
        {
            "Q": query,
            "Opts": {
                "TotalMaxMatchCount": max_results,
                "ShardMaxMatchCount": max_results,
                "MaxDocDisplayCount": max_results,
            },
        },
    )
    matches = _parse(document, max_results)

    wanted = {(shard.repository, shard.branch) for shard in shards}
    repositories = {repository for repository, _ in wanted}
    scoped: list[ZoektMatch] = []
    for match in matches:
        if match.repository not in repositories:
            continue
        # A shard built from a plain tree carries no branch metadata; excluding
        # it here would turn a real finding into silence.
        if match.branch is not None and (match.repository, match.branch) not in wanted:
            continue
        scoped.append(match)
    return scoped


def repository_file_count(shard: ShardRef) -> int:
    """Return how many documents the index holds for `shard`.

    This is what the inventory records as `files_scanned` on the indexed path:
    an index query reads no files itself, so the honest number is the size of
    the corpus the answer came from.
    """
    document = _post(LIST_PATH, {"Q": f"repo:^{_escape_re2(shard.repository)}$"})
    listing = document.get("List")
    if not isinstance(listing, dict):
        raise ZoektUnavailableError("zoekt-webserver list response carried no List")

    total = 0
    for entry in listing.get("Repos") or ():
        if not isinstance(entry, dict):
            continue
        stats = entry.get("Stats")
        if isinstance(stats, dict) and isinstance(stats.get("Documents"), int):
            total += stats["Documents"]
    return total


__all__ = [
    "DEFAULT_MAX_RESULTS",
    "LIST_PATH",
    "QUERY_TIMEOUT_SECONDS",
    "SEARCH_PATH",
    "ShardRef",
    "ZoektMatch",
    "build_query",
    "repository_file_count",
    "search",
    "search_shards",
]
