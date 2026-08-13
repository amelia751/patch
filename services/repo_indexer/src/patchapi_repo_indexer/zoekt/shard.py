"""Zoekt shard lifecycle (repo-indexer.md §5.2).

One shard directory per `(repository, branch)` under `ZOEKT_INDEX_DIR`, so a
repository imported by ten projects costs one index. This module only wraps the
`zoekt-git-index` / `zoekt-index` binaries; the reference counting that decides
when a shard may be dropped lives in `store.py`, because it is a fact about the
database rather than about the filesystem.

Missing binaries are not a crash. They are the condition `build_inventory`
degrades on: `ZoektUnavailableError` means "use the literal walk", and a shard
that exists but cannot be read means the same thing via `ShardCorruptError`. The
one outcome this module must never produce is a successful empty result.
"""

import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from patchapi_repo_indexer.config import ZOEKT_INDEX_DIR
from patchapi_repo_indexer.errors import ShardCorruptError, ZoektUnavailableError

ZOEKT_GIT_INDEX: Final[str] = "zoekt-git-index"
ZOEKT_INDEX: Final[str] = "zoekt-index"

# A cold index of a 484-file TypeScript repository takes ~1 s (repo-indexer.md
# §4.1). The ceiling is generous because it bounds a hung subprocess, not a
# slow one; exceeding it degrades to the literal walk rather than failing.
INDEX_TIMEOUT_SECONDS: Final[int] = 600

SHARD_SUFFIX: Final[str] = ".zoekt"

# `zoekt-index` names a repository after the directory it indexed unless it is
# handed metadata. The name it records is what `repo:` queries match, so without
# this the shard is addressed by a basename the query never asks for and every
# search returns zero hits — a repository reported clean because it was indexed
# under the wrong name. The file lives beside the shards it describes.
META_FILENAME: Final[str] = "repo-meta.json"

# Zoekt writes a header, a content section and a footer; anything this small is
# a partial write from an interrupted index, not a shard with no documents.
MIN_SHARD_BYTES: Final[int] = 64

# How much of a failed subprocess's stderr is carried into the error. Enough to
# name the cause, bounded so a runaway indexer cannot fill a log line.
_STDERR_TAIL_CHARS: Final[int] = 500

_UNSAFE_NAME_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True, slots=True)
class ShardRef:
    """The `(repository, branch)` pair a query is entitled to read."""

    repository: str
    branch: str = "main"


@dataclass(frozen=True, slots=True)
class ShardInfo:
    """A validated shard directory on disk."""

    repository: str
    branch: str
    path: Path
    shard_files: tuple[str, ...]
    size_bytes: int

    @property
    def ref(self) -> ShardRef:
        return ShardRef(repository=self.repository, branch=self.branch)


def shard_path_for(repository: str, branch: str) -> Path:
    """Return the shard directory for `(repository, branch)`.

    The directory name is a readable slug plus a digest of the exact pair. The
    slug cannot contain a separator or be `..` — the digest suffix guarantees
    that — so a repository named `../../etc` addresses a directory inside
    `ZOEKT_INDEX_DIR` like any other, and two projects importing the same
    repository resolve to the same shard.
    """
    key = f"{repository}@{branch}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    slug = _UNSAFE_NAME_RE.sub("_", key)[:48]
    return Path(ZOEKT_INDEX_DIR) / f"{slug}-{digest}"


def binaries_available() -> bool:
    """True when both indexer binaries are on PATH."""
    return all(shutil.which(name) is not None for name in (ZOEKT_GIT_INDEX, ZOEKT_INDEX))


def _binary(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise ZoektUnavailableError(f"{name} is not on PATH")
    return found


def _run(command: Sequence[str]) -> None:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=INDEX_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ZoektUnavailableError(f"{command[0]} disappeared before it could run") from exc
    except subprocess.TimeoutExpired as exc:
        raise ZoektUnavailableError(f"{command[0]} exceeded {INDEX_TIMEOUT_SECONDS}s") from exc
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip()[-_STDERR_TAIL_CHARS:]
        raise ZoektUnavailableError(f"{command[0]} exited {completed.returncode}: {tail}")


def _write_meta(directory: Path, repository: str) -> Path:
    """Record the logical repository name for `zoekt-index` to index under."""
    meta_path = directory / META_FILENAME
    try:
        meta_path.write_text(json.dumps({"Name": repository}), encoding="utf-8")
    except OSError as exc:
        raise ZoektUnavailableError(f"cannot write shard metadata to {meta_path}") from exc
    return meta_path


def _validate_shard(repository: str, branch: str, directory: Path) -> ShardInfo:
    """Read the shard directory, refusing to call an unreadable index empty.

    An absent directory is `ZoektUnavailableError` — nothing has been indexed
    yet. A directory that exists but holds no usable shard is
    `ShardCorruptError`, because at that point something did index and the
    result cannot be trusted. Both degrade to the literal walk; they are
    distinguished so the audit event says which happened.
    """
    if not directory.is_dir():
        raise ZoektUnavailableError(f"no shard for {repository}@{branch} at {directory}")

    try:
        candidates = sorted(path for path in directory.iterdir() if path.suffix == SHARD_SUFFIX)
    except OSError as exc:
        raise ShardCorruptError(f"shard directory for {repository}@{branch} is unreadable") from exc

    if not candidates:
        raise ShardCorruptError(f"shard directory for {repository}@{branch} holds no shard file")

    total = 0
    for candidate in candidates:
        try:
            size = candidate.stat().st_size
        except OSError as exc:
            raise ShardCorruptError(f"shard file {candidate.name} cannot be stat'd") from exc
        if size < MIN_SHARD_BYTES:
            raise ShardCorruptError(
                f"shard file {candidate.name} is {size} bytes: truncated, not empty"
            )
        total += size

    return ShardInfo(
        repository=repository,
        branch=branch,
        path=directory,
        shard_files=tuple(path.name for path in candidates),
        size_bytes=total,
    )


def shard_info(repository: str, branch: str) -> ShardInfo:
    """Return the shard for `(repository, branch)` without rebuilding it."""
    return _validate_shard(repository, branch, shard_path_for(repository, branch))


def index_repository(repo_path: Path, repository: str, branch: str) -> ShardInfo:
    """Build or refresh the shard for `(repository, branch)` from `repo_path`.

    A git checkout is indexed by ref through `zoekt-git-index`, which is
    incremental: re-running it against an unchanged tree reuses the shard. A
    plain directory — a sandbox workspace, a fixture tree — has no refs, so it
    is indexed as files by `zoekt-index`.
    """
    if not repo_path.is_dir():
        raise ZoektUnavailableError(f"cannot index a path that is not a directory: {repo_path}")

    directory = shard_path_for(repository, branch)
    is_git = (repo_path / ".git").exists()
    binary = _binary(ZOEKT_GIT_INDEX if is_git else ZOEKT_INDEX)

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ZoektUnavailableError(f"cannot create shard directory {directory}") from exc

    if is_git:
        command = [binary, "-index", str(directory), "-branches", branch, str(repo_path)]
    else:
        command = [
            binary,
            "-index",
            str(directory),
            "-meta",
            str(_write_meta(directory, repository)),
            str(repo_path),
        ]

    _run(command)
    return _validate_shard(repository, branch, directory)


def delta_index(
    repo_path: Path, repository: str, branch: str, changed_paths: Sequence[str]
) -> ShardInfo:
    """Refresh the shard for the files a push touched.

    For a git checkout this re-runs the incremental git indexer: zoekt already
    reuses everything the push did not move, which is the ~0.13 s number in
    repo-indexer.md §4.1, and re-running it keeps deletions out of the shard —
    something an additive per-file index cannot do. `changed_paths` is therefore
    a statement of what moved, not a list of arguments.

    For a non-git tree there is no ref to diff against, so the tree is re-indexed
    whole and the caller narrows the result to the paths that moved. Handing
    `zoekt-index` the changed files individually would be faster and wrong: it
    records each argument under the path it was given, so a file indexed as
    `/work/src/image.ts` never matches the `src/image.ts` a changed-paths scan
    filters on, and the scan reports no usages at all.
    """
    if (repo_path / ".git").exists():
        return index_repository(repo_path, repository, branch)

    directory = shard_path_for(repository, branch)
    if not any((repo_path / candidate).is_file() for candidate in changed_paths):
        # Every changed path was a deletion: the shard on disk is still the best
        # answer available, and reporting it beats reporting nothing.
        return _validate_shard(repository, branch, directory)

    return index_repository(repo_path, repository, branch)


__all__ = [
    "INDEX_TIMEOUT_SECONDS",
    "META_FILENAME",
    "MIN_SHARD_BYTES",
    "SHARD_SUFFIX",
    "ZOEKT_GIT_INDEX",
    "ZOEKT_INDEX",
    "ShardInfo",
    "ShardRef",
    "binaries_available",
    "delta_index",
    "index_repository",
    "shard_info",
    "shard_path_for",
]
