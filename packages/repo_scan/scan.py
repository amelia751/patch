"""Deterministic identifier search over a checkout (roadmap §7.4, §11.3).

Layer A of impact analysis: find the literal provider identifiers — model IDs,
endpoint paths, import names — that a change manifest lists. No model runs
here, so the same commit always yields the same inventory, and the LLM later
reasons over candidate snippets instead of reading every byte of the repo.
"""

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from packages.repo_scan.classify import RUNTIME_USAGE_KINDS, UsageKind, classify_path
from packages.repo_scan.config import (
    MAX_EXCERPT_CHARS,
    MAX_FILE_BYTES,
    SCANNED_EXTENSIONS,
    SCANNED_FILENAMES,
    SCANNER_VERSION,
    SKIP_DIRECTORIES,
)


@dataclass(frozen=True, slots=True)
class IdentifierHit:
    """One literal occurrence of a provider identifier."""

    path: str
    line_number: int
    identifier: str
    excerpt: str
    usage_kind: UsageKind

    @property
    def is_runtime(self) -> bool:
        return self.usage_kind in RUNTIME_USAGE_KINDS


@dataclass(frozen=True, slots=True)
class ScanResult:
    scanner_version: str
    root: str
    identifiers: tuple[str, ...]
    hits: tuple[IdentifierHit, ...]
    files_scanned: int

    @property
    def matched_identifiers(self) -> tuple[str, ...]:
        return tuple(sorted({hit.identifier for hit in self.hits}))

    @property
    def runtime_hits(self) -> tuple[IdentifierHit, ...]:
        return tuple(hit for hit in self.hits if hit.is_runtime)


def should_scan_file(path: Path) -> bool:
    """True when `path` is a text file this scanner is willing to read."""
    if path.name in SCANNED_FILENAMES:
        return True
    return path.suffix.lower() in SCANNED_EXTENSIONS


def scan_text(text: str, identifiers: Iterable[str], *, path: str) -> list[IdentifierHit]:
    """Return every occurrence of `identifiers` in `text`, in file order.

    Matching is literal and case-sensitive: a model ID is an exact string, and
    a fuzzy match here would put a fabricated finding in front of a reviewer.
    """
    wanted = tuple(dict.fromkeys(identifier for identifier in identifiers if identifier))
    if not wanted:
        return []

    usage_kind = classify_path(path)
    hits: list[IdentifierHit] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for identifier in wanted:
            if identifier in line:
                hits.append(
                    IdentifierHit(
                        path=path,
                        line_number=line_number,
                        identifier=identifier,
                        excerpt=line.strip()[:MAX_EXCERPT_CHARS],
                        usage_kind=usage_kind,
                    )
                )
    return hits


def scan_tree(root: Path | str, identifiers: Sequence[str]) -> ScanResult:
    """Walk `root` and report every literal hit for `identifiers`.

    Traversal is sorted at every level, so the hit order is a property of the
    commit rather than of the filesystem.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        raise NotADirectoryError(f"scan root is not a directory: {root_path}")

    wanted = tuple(dict.fromkeys(identifier for identifier in identifiers if identifier))
    hits: list[IdentifierHit] = []
    files_scanned = 0

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRECTORIES)
        for filename in sorted(filenames):
            file_path = Path(dirpath) / filename
            if not should_scan_file(file_path):
                continue
            try:
                if file_path.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                # Unreadable or binary: skipped, never guessed at. A file that
                # cannot be read deterministically produces no finding.
                continue
            files_scanned += 1
            relative = file_path.relative_to(root_path).as_posix()
            hits.extend(scan_text(text, wanted, path=relative))

    return ScanResult(
        scanner_version=SCANNER_VERSION,
        root=str(root_path),
        identifiers=wanted,
        hits=tuple(hits),
        files_scanned=files_scanned,
    )
