"""Capturing the provider bytes a change was read from.

Policy fails closed on a change with no hashed source snapshot, which is the
right rule and, until now, one nothing could satisfy: the ingest path stored a
notice's *title and summary* and the URL they came from, never the page itself.
Every run therefore stopped at HUMAN_REQUIRED with "no hashed provider snapshot
backs this change" — an accurate complaint about a missing capture step rather
than about the change.

This is that step. It fetches each cited URL, stores the bytes, and hashes them,
so a reviewer reading a pull request can fetch the same digest and confirm the
agents read what the pull request says they read.

Three things this deliberately does not do. It does not parse the page: provider
text is untrusted input, and the only claim made here is "these are the bytes
that were served". It does not retry forever or follow a page into an unbounded
download; a capture that cannot be taken cheaply is better recorded as absent,
because absent means HUMAN_REQUIRED and that is a safe answer. And it never
invents a digest for a fetch that failed — an empty capture is not evidence.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import httpx

from packages.schemas.evidence import SourceSnapshot

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

log = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS: Final[float] = 20.0

# A release note is kilobytes. A megabyte cap keeps a mis-pointed URL — a tarball,
# a video — from turning a capture into a memory problem, and a page that large
# is not the notice anyway.
MAX_CAPTURE_BYTES: Final[int] = 1 << 20

# PatchAPI identifies itself. A provider blocking an unmarked scraper should be
# able to tell what this is.
USER_AGENT: Final[str] = "PatchAPI-evidence-capture/1.0 (+https://github.com/patchapi)"

# Where a captured page is addressable from. In Cloud Run this is the service's
# own URL, so `content_uri` is a link a reviewer can open. Unset — a laptop with
# no public address — falls back to a file:// path written on demand, which is
# equally re-hashable and does not pretend to be reachable.
EVIDENCE_BASE_ENV: Final[str] = "PATCHAPI_EVIDENCE_BASE_URL"
EVIDENCE_PATH: Final[str] = "/v1/evidence"


class CaptureError(RuntimeError):
    """The page could not be fetched, so there is nothing to hash."""


@dataclass(frozen=True, slots=True)
class Capture:
    """Bytes served for one URL, and their digest."""

    source_url: str
    body: str
    content_sha256: str
    media_type: str
    retrieved_at: datetime

    @property
    def size_bytes(self) -> int:
        return len(self.body.encode("utf-8"))


def digest(body: str) -> str:
    """Lowercase sha256 of `body` as UTF-8, the form stored and served."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


async def fetch(url: str, *, client: httpx.AsyncClient | None = None) -> Capture:
    """Fetch `url` and hash what came back.

    Raises `CaptureError` rather than returning an empty capture: a change with
    no evidence must stay a change with no evidence, so that policy sees the gap.
    """
    owned = client is None
    session = client or httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        response = await session.get(url)
        response.raise_for_status()
        raw = response.content[:MAX_CAPTURE_BYTES]
        media_type = (response.headers.get("content-type") or "text/html").split(";")[0].strip()
    except httpx.HTTPError as exc:
        raise CaptureError(f"cannot capture {url}: {exc}") from exc
    finally:
        if owned:
            await session.aclose()

    body = raw.decode("utf-8", errors="replace")
    if not body.strip():
        raise CaptureError(f"{url} served nothing to hash")
    return Capture(
        source_url=url,
        body=body,
        content_sha256=digest(body),
        media_type=media_type or "text/html",
        retrieved_at=datetime.now(UTC),
    )


_STORE_SQL: Final[str] = """
INSERT INTO change_event_snapshots (
    change_event_id, source_url, content_sha256, media_type, body, size_bytes, retrieved_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (change_event_id, source_url) DO UPDATE SET
    content_sha256 = EXCLUDED.content_sha256,
    media_type     = EXCLUDED.media_type,
    body           = EXCLUDED.body,
    size_bytes     = EXCLUDED.size_bytes,
    retrieved_at   = EXCLUDED.retrieved_at
RETURNING id
"""

# The dashboard reads a single digest off the change to say whether evidence
# exists at all, so the first capture taken is mirrored there.
_MARK_EVENT_SQL: Final[str] = """
UPDATE change_events
SET source_sha256 = $2, source_uri = $3
WHERE id = $1 AND COALESCE(source_sha256, '') = ''
"""

_URLS_SQL: Final[str] = "SELECT source_urls FROM change_events WHERE id = $1"

_LOAD_SQL: Final[str] = """
SELECT source_url, content_sha256, media_type, body, retrieved_at
FROM change_event_snapshots
WHERE change_event_id = $1
ORDER BY retrieved_at
"""

_BY_DIGEST_SQL: Final[str] = """
SELECT source_url, content_sha256, media_type, body, retrieved_at
FROM change_event_snapshots
WHERE content_sha256 = $1
LIMIT 1
"""


async def store(
    connection: asyncpg.Connection, change_event_id: UUID | str, capture: Capture
) -> None:
    """Persist one capture against a change event."""
    event_id = _as_uuid(change_event_id)
    await connection.fetchval(
        _STORE_SQL,
        event_id,
        capture.source_url,
        capture.content_sha256,
        capture.media_type,
        capture.body,
        capture.size_bytes,
        capture.retrieved_at,
    )
    await connection.execute(
        _MARK_EVENT_SQL, event_id, capture.content_sha256, content_uri(capture.content_sha256)
    )


async def capture_event(
    connection: asyncpg.Connection,
    change_event_id: UUID | str,
    *,
    urls: list[str] | None = None,
) -> list[Capture]:
    """Capture every URL a change cites, and keep whichever ones answered.

    A URL that fails is logged and skipped rather than raised. Some notices cite
    three pages and one of them 404s; one good capture is still evidence, and no
    captures at all still reads as an evidence gap downstream.
    """
    event_id = _as_uuid(change_event_id)
    cited = urls if urls is not None else list(await connection.fetchval(_URLS_SQL, event_id) or [])
    if not cited:
        return []

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        results = await asyncio.gather(
            *(fetch(url, client=client) for url in cited), return_exceptions=True
        )

    taken: list[Capture] = []
    for url, result in zip(cited, results, strict=True):
        if isinstance(result, Capture):
            await store(connection, event_id, result)
            taken.append(result)
        else:
            log.warning("no snapshot for %s: %s", url, result)
    if taken:
        log.info("captured %d/%d sources for change %s", len(taken), len(cited), event_id)
    return taken


async def load(connection: asyncpg.Connection, change_event_id: UUID | str) -> list[SourceSnapshot]:
    """The stored captures, as the evidence objects a manifest carries."""
    rows = await connection.fetch(_LOAD_SQL, _as_uuid(change_event_id))
    snapshots: list[SourceSnapshot] = []
    for row in rows:
        uri = content_uri(row["content_sha256"])
        if uri.startswith("file://"):
            # A citation that does not resolve is not a citation. With no public
            # base URL the bytes have to exist on this filesystem before the URI
            # naming them goes into a manifest.
            materialize(row["body"], row["content_sha256"])
        try:
            snapshots.append(
                SourceSnapshot(
                    source_url=row["source_url"],
                    retrieved_at=row["retrieved_at"],
                    content_uri=uri,
                    content_sha256=row["content_sha256"],
                    media_type=row["media_type"] or "text/html",
                )
            )
        except ValueError as exc:
            # A stored row that no longer satisfies the evidence schema is a gap,
            # not a reason to fail the run that asked for it.
            log.warning("discarding unusable snapshot for %s: %s", row["source_url"], exc)
    return snapshots


async def read_by_digest(connection: asyncpg.Connection, sha256: str) -> dict[str, Any] | None:
    """One capture, addressed the way a pull request body cites it."""
    row = await connection.fetchrow(_BY_DIGEST_SQL, sha256.strip().lower())
    return dict(row) if row is not None else None


def content_uri(sha256: str) -> str:
    """Where the bytes behind `sha256` can be fetched and re-hashed.

    `SourceSnapshot` only permits gs://, https:// and file://, which is what
    makes the field worth having: a scheme a reviewer cannot dereference is not
    a citation. With a public base URL configured this is that service's
    evidence route; without one it is a file this process can write.
    """
    base = os.environ.get(EVIDENCE_BASE_ENV, "").strip().rstrip("/")
    if base.startswith("https://"):
        return f"{base}{EVIDENCE_PATH}/{sha256}"
    return (_evidence_dir() / f"{sha256}.txt").as_uri()


def materialize(capture_body: str, sha256: str) -> Path:
    """Write bytes to the local evidence path so a file:// URI resolves.

    Only used when no public base URL is configured. The digest is the filename,
    so a second write of the same bytes is a no-op and a tampered file is
    detectable by re-hashing.
    """
    path = _evidence_dir() / f"{sha256}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(capture_body, encoding="utf-8")
    return path


def _evidence_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / ".local" / "evidence"


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


__all__ = [
    "EVIDENCE_BASE_ENV",
    "EVIDENCE_PATH",
    "MAX_CAPTURE_BYTES",
    "Capture",
    "CaptureError",
    "capture_event",
    "content_uri",
    "digest",
    "fetch",
    "load",
    "materialize",
    "read_by_digest",
    "store",
]
