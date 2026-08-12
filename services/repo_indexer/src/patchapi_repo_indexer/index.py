"""Build an API usage inventory for a local checkout (roadmap §11.1 to §11.3).

This is Layer A and nothing else: literal identifier search with a stable
ordering, so the same commit always produces the same inventory and the
expensive reasoning layers are handed candidate snippets instead of a repo.

Two entry points, matching the two ways the index is maintained: a full scan
when a repository is first indexed, and a changed-paths scan when a push
webhook says which files moved.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path

from packages.repo_scan import IdentifierHit, scan_text, scan_tree, should_scan_file
from packages.repo_scan.config import MAX_FILE_BYTES
from patchapi_repo_indexer.config import (
    DEFAULT_PROVIDER,
    LITERAL_MATCH_CONFIDENCE,
    SCOPE_CHANGED_PATHS,
    SCOPE_FULL_TREE,
    watchlist_for,
)
from patchapi_repo_indexer.errors import ScanRootError, UnsafePathError
from patchapi_repo_indexer.models import ApiUsageInventory, ApiUsageRecord


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
) -> ApiUsageInventory:
    """Index `root` for `provider`'s watched identifiers at `observed_sha`.

    Passing `changed_paths` narrows the scan to those files and marks the
    result as partial, so a push-driven update is never mistaken for a complete
    picture of the repository.
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
        observed_sha=observed_sha,
        provider=provider,
        watched_identifiers=wanted,
        scope=scope,
        files_scanned=files_scanned,
        usages=tuple(_record(hit, provider) for hit in hits),
    )
