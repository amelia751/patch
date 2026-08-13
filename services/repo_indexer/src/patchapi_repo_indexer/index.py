"""Build an API usage inventory for a local checkout (roadmap §11.1 to §11.3).

Layer A, by two interchangeable routes. `build_inventory_zoekt` queries a Zoekt
shard with the provider's family regexes, which finds model IDs nobody
enumerated and answers without re-reading the tree. `build_inventory_literal`
walks the checkout for the pinned watchlist. Both produce the same
`ApiUsageInventory`, and `build_inventory` picks between them.

The choice fails soft in one direction only: an unreachable index degrades to
the walk, because a slower answer with lower recall is tolerable and a
repository reported as clean because the index was down is not.

Two scopes, matching the two ways the index is maintained: a full scan when a
repository is first indexed, and a changed-paths scan when a push webhook says
which files moved.
"""

import logging
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from packages.repo_scan import IdentifierHit, scan_text, scan_tree, should_scan_file
from packages.repo_scan.classify import classify_path
from packages.repo_scan.config import MAX_FILE_BYTES
from patchapi_repo_indexer.astgrep.runner import StructuralMatch, configured_rule_dir, scan_files
from patchapi_repo_indexer.config import (
    DEFAULT_PROVIDER,
    INDEX_BACKEND,
    LITERAL_MATCH_CONFIDENCE,
    SCOPE_CHANGED_PATHS,
    SCOPE_FULL_TREE,
    watchlist_for,
)
from patchapi_repo_indexer.errors import (
    AstGrepRuleError,
    ScanRootError,
    ShardCorruptError,
    UnsafePathError,
    ZoektUnavailableError,
)
from patchapi_repo_indexer.models import MAX_EXCERPT_CHARS, ApiUsageInventory, ApiUsageRecord
from patchapi_repo_indexer.zoekt import patterns as zoekt_patterns
from patchapi_repo_indexer.zoekt import query as zoekt_query
from patchapi_repo_indexer.zoekt import shard as zoekt_shard

log = logging.getLogger(__name__)

# The backend that reads an index rather than the tree. Any other value selects
# the literal walk outright, without attempting a shard.
ZOEKT_BACKEND = "zoekt"


def _resolve_root(root: Path | str) -> Path:
    root_path = Path(root)
    if not root_path.exists():
        raise ScanRootError(f"scan root does not exist: {root_path}")
    if not root_path.is_dir():
        raise ScanRootError(f"scan root is not a directory: {root_path}")
    return root_path


def _resolve_identifiers(provider: str, identifiers: Sequence[str] | None) -> tuple[str, ...]:
    """Return the identifiers to search for, deduplicated in caller order.

    An explicitly supplied but empty list is refused rather than treated as the
    pinned watchlist: "search for nothing" and "search for the default" are
    different requests, and only one of them can be made by accident.
    """
    if identifiers is None:
        return watchlist_for(provider)
    wanted = tuple(dict.fromkeys(value.strip() for value in identifiers if value.strip()))
    if not wanted:
        raise ValueError("identifiers was supplied but contains no non-empty value")
    return wanted


def _record(hit: IdentifierHit, provider: str) -> ApiUsageRecord:
    return ApiUsageRecord(
        provider=provider,
        identifier=hit.identifier,
        file_path=hit.path,
        line_start=hit.line_number,
        line_end=hit.line_number,
        usage_kind=hit.usage_kind,
        confidence=LITERAL_MATCH_CONFIDENCE,
        excerpt=hit.excerpt,
    )


def _safe_relative(root: Path, candidate: str) -> Path:
    """Resolve a repo-relative path inside `root`, refusing anything that escapes.

    Changed paths arrive from a webhook payload, which is external input. A
    path that resolves outside the checkout is an attempt to read a file this
    scan has no business reading, so it stops the scan instead of being skipped.
    """
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise UnsafePathError(f"path escapes the scan root: {candidate!r}")
    return resolved


def _scan_changed_paths(
    root: Path, changed_paths: Iterable[str], identifiers: Sequence[str]
) -> tuple[list[IdentifierHit], int]:
    """Scan only the named paths, in sorted order.

    A path that no longer exists is not an error: a push that deletes a file
    should retire its rows, and a deleted file simply yields no hit.
    """
    hits: list[IdentifierHit] = []
    files_scanned = 0
    for relative in sorted(dict.fromkeys(changed_paths)):
        file_path = _safe_relative(root, relative)
        if not file_path.is_file() or not should_scan_file(file_path):
            continue
        try:
            if file_path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Consistent with the tree walk: an unreadable file produces no
            # finding rather than a guessed one.
            continue
        files_scanned += 1
        hits.extend(scan_text(text, identifiers, path=Path(relative).as_posix()))
    return hits, files_scanned


def build_inventory(
    *,
    root: Path | str,
    repository: str,
    observed_sha: str,
    provider: str = DEFAULT_PROVIDER,
    identifiers: Sequence[str] | None = None,
    changed_paths: Sequence[str] | None = None,
    branch: str = "main",
) -> ApiUsageInventory:
    """Index `root` for `provider`'s watched identifiers at `observed_sha`.

    Uses the Zoekt backend when it is selected and reachable, and the literal
    walk otherwise. The degradation is logged rather than silent: a fallback
    that nobody can see looks exactly like a healthy index (repo-indexer.md
    §10).

    Passing `changed_paths` narrows the scan to those files and marks the
    result as partial, so a push-driven update is never mistaken for a complete
    picture of the repository.
    """
    if INDEX_BACKEND == ZOEKT_BACKEND:
        try:
            return build_inventory_zoekt(
                root=root,
                repository=repository,
                observed_sha=observed_sha,
                provider=provider,
                identifiers=identifiers,
                changed_paths=changed_paths,
                branch=branch,
            )
        except (ZoektUnavailableError, ShardCorruptError) as exc:
            log.warning(
                "zoekt unavailable, falling back to literal scan:"
                " repository=%s branch=%s reason=%s",
                repository,
                branch,
                exc,
            )

    return build_inventory_literal(
        root=root,
        repository=repository,
        observed_sha=observed_sha,
        provider=provider,
        identifiers=identifiers,
        changed_paths=changed_paths,
        branch=branch,
    )


def build_inventory_literal(
    *,
    root: Path | str,
    repository: str,
    observed_sha: str,
    provider: str = DEFAULT_PROVIDER,
    identifiers: Sequence[str] | None = None,
    changed_paths: Sequence[str] | None = None,
    branch: str = "main",
) -> ApiUsageInventory:
    """Index `root` by walking it for the pinned literal watchlist.

    The fallback backend, and the only one that needs no binary, no index and no
    server. It finds exactly what it was told to look for.
    """
    root_path = _resolve_root(root)
    wanted = _resolve_identifiers(provider, identifiers)

    if changed_paths is None:
        result = scan_tree(root_path, wanted)
        hits: Sequence[IdentifierHit] = result.hits
        files_scanned = result.files_scanned
        scope = SCOPE_FULL_TREE
    else:
        hits, files_scanned = _scan_changed_paths(root_path, changed_paths, wanted)
        scope = SCOPE_CHANGED_PATHS

    return ApiUsageInventory(
        repository=repository,
        branch=branch,
        observed_sha=observed_sha,
        provider=provider,
        watched_identifiers=wanted,
        scope=scope,
        files_scanned=files_scanned,
        usages=tuple(_record(hit, provider) for hit in hits),
    )


def _changed_path_set(root: Path, changed_paths: Iterable[str]) -> set[str]:
    """Return the scannable subset of `changed_paths`.

    Path safety is checked here for the same reason the walk checks it: a
    changed path arrives from a webhook, and one that resolves outside the
    checkout is an attempt to read a file this scan has no business reading.
    """
    kept: set[str] = set()
    for relative in sorted(dict.fromkeys(changed_paths)):
        file_path = _safe_relative(root, relative)
        if file_path.is_file() and should_scan_file(file_path):
            kept.add(Path(relative).as_posix())
    return kept


def _confirmed_lines(matches: Sequence[StructuralMatch]) -> dict[str, list[StructuralMatch]]:
    grouped: dict[str, list[StructuralMatch]] = {}
    for match in matches:
        grouped.setdefault(match.path, []).append(match)
    return grouped


def _surface_for(
    grouped: dict[str, list[StructuralMatch]], path: str, line_number: int
) -> str | None:
    for match in grouped.get(path, ()):
        if match.line_start <= line_number <= match.line_end:
            return match.rule_id
    return None


def _confirm_structurally(
    root: Path, records: Sequence[ApiUsageRecord]
) -> tuple[ApiUsageRecord, ...]:
    """Annotate the records ast-grep confirms are call sites or configuration.

    Confirmation sets `surface` to the rule that matched; an unconfirmed record
    is left exactly as Layer A produced it rather than dropped. A rule cannot
    prove the absence of a usage — it only recognises the shapes it was written
    for — so treating "no rule matched" as "no finding" would convert a gap in
    the rule set into a false negative (hard constraint #10).
    """
    if not records:
        return tuple(records)

    candidates = sorted({record.file_path for record in records})
    try:
        matches = scan_files(configured_rule_dir(), [root / path for path in candidates], root)
    except AstGrepRuleError as exc:
        # Layer B is precision. Its failure downgrades the ranking, never the
        # inventory, so the Layer A rows are returned untouched.
        log.warning("ast-grep layer B skipped: %s", exc)
        return tuple(records)

    grouped = _confirmed_lines(matches)
    return tuple(
        record.model_copy(update={"surface": surface})
        if (surface := _surface_for(grouped, record.file_path, record.line_start))
        else record
        for record in records
    )


def _zoekt_records(
    matches: Sequence[zoekt_query.ZoektMatch],
    provider: str,
    compiled: Sequence[re.Pattern[str]],
    allowed_paths: set[str] | None,
) -> list[ApiUsageRecord]:
    """Turn matched lines into inventory rows, one row per identifier per line.

    The identifier recorded is the text the pattern actually matched, not the
    pattern: the point of querying an index with a family regex is to name the
    concrete model ID a repository uses, including ones no watchlist listed.
    """
    seen: set[tuple[str, int, str]] = set()
    records: list[ApiUsageRecord] = []
    for match in matches:
        path = Path(match.path).as_posix()
        if allowed_paths is not None and path not in allowed_paths:
            continue
        for identifier in zoekt_patterns.match_identifiers(match.line, compiled):
            key = (path, match.line_number, identifier)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                ApiUsageRecord(
                    provider=provider,
                    identifier=identifier,
                    file_path=path,
                    line_start=match.line_number,
                    line_end=match.line_number,
                    usage_kind=classify_path(path),
                    confidence=LITERAL_MATCH_CONFIDENCE,
                    excerpt=match.line.strip()[:MAX_EXCERPT_CHARS],
                )
            )
    records.sort(key=lambda record: (record.file_path, record.line_start, record.identifier))
    return records


def build_inventory_zoekt(
    *,
    root: Path | str,
    repository: str,
    observed_sha: str,
    provider: str = DEFAULT_PROVIDER,
    identifiers: Sequence[str] | None = None,
    changed_paths: Sequence[str] | None = None,
    branch: str = "main",
) -> ApiUsageInventory:
    """Index `root` by querying a Zoekt shard, then confirming with ast-grep.

    Raises `ZoektUnavailableError` or `ShardCorruptError` when the index cannot
    be built or read. It never returns an empty inventory to mean that:
    `build_inventory` catches both and degrades to the literal walk.

    `watched_identifiers` still records what the caller asked to watch. What the
    query found may be a superset — that is the recall the index buys — and the
    two are kept separate so a reviewer can tell a pinned identifier from a
    family member the pattern caught.
    """
    root_path = _resolve_root(root)
    wanted = _resolve_identifiers(provider, identifiers)
    patterns = zoekt_patterns.patterns_for(provider, wanted)
    compiled = zoekt_patterns.compile_patterns(patterns)

    if changed_paths is None:
        shard = zoekt_shard.index_repository(root_path, repository, branch)
        allowed_paths = None
        scope = SCOPE_FULL_TREE
    else:
        allowed_paths = _changed_path_set(root_path, changed_paths)
        shard = zoekt_shard.delta_index(root_path, repository, branch, sorted(allowed_paths))
        scope = SCOPE_CHANGED_PATHS

    # How many documents the query's own scope can see, asked before the query
    # rather than after it. A `repo:` term that matches no indexed repository
    # returns zero hits and HTTP 200, which is byte-for-byte the answer a clean
    # repository gives. Checking the corpus size is what tells the two apart:
    # zero documents means the shard was never loaded or was indexed under a
    # different name, and neither is evidence that nothing is affected.
    indexed_documents = zoekt_query.repository_file_count(shard.ref)
    if indexed_documents == 0:
        raise ShardCorruptError(
            f"shard for {repository}@{branch} exposes no documents to a"
            f" repo:{repository} query; refusing to read that as an unaffected repository"
        )

    matches = zoekt_query.search_shards(patterns, [shard.ref])
    records = _zoekt_records(matches, provider, compiled, allowed_paths)

    if changed_paths is None:
        # An index query reads no files of its own, so the honest count is the
        # size of the corpus the answer came from.
        files_scanned = indexed_documents
    else:
        files_scanned = len(allowed_paths or ())

    return ApiUsageInventory(
        repository=repository,
        branch=branch,
        observed_sha=observed_sha,
        provider=provider,
        watched_identifiers=wanted,
        scope=scope,
        files_scanned=files_scanned,
        usages=_confirm_structurally(root_path, records),
    )
