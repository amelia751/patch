"""Hashed captures of official provider pages.

A `ChangeManifest` that cites a URL proves nothing: the page can be rewritten
between the run and the review. A snapshot pins the bytes the agents actually
read, so a reviewer can re-hash the file and confirm.

Capture is deliberately offline here. Fetching is a separate, auditable step;
this module only hashes what is already on disk and verifies it later.
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from packages.schemas.evidence import SourceSnapshot

# Read in chunks so a large captured page never has to be held twice.
_HASH_CHUNK_BYTES = 1 << 20


def sha256_hex(data: bytes) -> str:
    """Lowercase sha256 digest of `data`."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Lowercase sha256 digest of the file at `path`."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_from_file(
    *,
    source_url: str,
    path: Path,
    retrieved_at: datetime | None = None,
    media_type: str = "text/html",
) -> SourceSnapshot:
    """Hash a captured page on disk into a `SourceSnapshot`.

    Raises `FileNotFoundError` rather than emitting a snapshot for bytes that
    are not there.
    """
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"no captured page at {resolved}")
    return SourceSnapshot(
        source_url=source_url,
        retrieved_at=retrieved_at or datetime.now(UTC),
        content_uri=resolved.as_uri(),
        content_sha256=sha256_file(resolved),
        media_type=media_type,
    )


def snapshot_matches_file(snapshot: SourceSnapshot, path: Path) -> bool:
    """Whether the bytes at `path` still hash to what `snapshot` recorded."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return False
    return sha256_file(resolved) == snapshot.content_sha256
