"""Google Cloud release notes snapshot (last 365 days).

This is not Service Usage. The public BigQuery table is one job, not a 1 QPS
list, and a year of notes is thousands of rows. Serving reads the committed
JSON. Refresh runs the query and rewrites the file. Provider text is untrusted.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Final

import httpx

from packages.state.gcp_catalog import (
    CatalogUnavailableError,
    _mint_token,
    credentials_path,
    project_id,
)

NOTES_FILENAME: Final[str] = "google_release_notes.json"
TABLE: Final[str] = "bigquery-public-data.google_cloud_release_notes.release_notes"
WINDOW_DAYS: Final[int] = 365
SUMMARY_LIMIT: Final[int] = 280
QUERY_TIMEOUT_MS: Final[int] = 60_000
PAGE_SIZE: Final[int] = 1_000
REQUEST_TIMEOUT_SECONDS: Final[float] = 60.0
SOURCE_URL: Final[str] = "https://cloud.google.com/release-notes"

_TYPE_TO_KIND: Final[dict[str, str]] = {
    "DEPRECATION": "deprecation",
    "BREAKING_CHANGE": "breaking_change",
    "FEATURE": "feature",
    "FIX": "fix",
    "ISSUE": "issue",
    "SECURITY_BULLETIN": "security",
    "SERVICE_ANNOUNCEMENT": "announcement",
    "NON_BREAKING_CHANGE": "change",
    "LIBRARIES": "libraries",
    "OTHER": "other",
}

_TABLE_PART: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]+$")


def release_notes_query(qualified_table: str) -> str:
    """Return the notes SELECT. Table parts must be identifiers."""
    parts = qualified_table.split(".")
    if len(parts) != 3 or not all(_TABLE_PART.fullmatch(part) for part in parts):
        raise CatalogUnavailableError("release notes table is not a qualified BigQuery id")
    table = ".".join(parts)
    return f"""
SELECT
  CAST(published_at AS STRING) AS published_at,
  product_name,
  release_note_type,
  IFNULL(product_version_name, "") AS product_version_name,
  description
FROM `{table}`
WHERE published_at >= DATE_SUB(CURRENT_DATE(), INTERVAL {WINDOW_DAYS} DAY)
ORDER BY published_at DESC, product_name
"""


_SELECT: Final[str] = release_notes_query(TABLE)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._parts)).strip()


@dataclass(frozen=True)
class ReleaseNote:
    id: str
    product: str
    kind: str
    release_note_type: str
    title: str
    summary: str
    published_at: str
    source_url: str


@dataclass(frozen=True)
class ReleaseNotesSnapshot:
    fetched_at: str
    window_days: int
    source: str
    notes: tuple[ReleaseNote, ...]


def notes_path(*, base_dir: Path | None = None) -> Path:
    root = Path(__file__).resolve().parent if base_dir is None else base_dir
    return root / "data" / NOTES_FILENAME


def strip_html(raw: str) -> str:
    parser = _HTMLText()
    try:
        parser.feed(raw or "")
        parser.close()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw or "")).strip()
    return parser.text()


def note_kind(release_note_type: str) -> str:
    return _TYPE_TO_KIND.get((release_note_type or "").strip().upper(), "other")


def _note_id(
    product: str,
    published_at: str,
    note_type: str,
    version: str,
    description: str,
) -> str:
    material = f"{product}|{published_at}|{note_type}|{version}|{description}".encode()
    return f"rn:{hashlib.sha256(material).hexdigest()[:20]}"


def uniquify_note_ids(notes: tuple[ReleaseNote, ...]) -> tuple[ReleaseNote, ...]:
    """Disambiguate identical changelog rows so React keys stay unique."""
    seen: dict[str, int] = {}
    unique: list[ReleaseNote] = []
    for note in notes:
        count = seen.get(note.id, 0) + 1
        seen[note.id] = count
        unique.append(note if count == 1 else replace(note, id=f"{note.id}:{count}"))
    return tuple(unique)


_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def published_day(value: str) -> str:
    day = (value or "").strip()[:10]
    return day if _DAY.fullmatch(day) else ""


def filter_notes(
    notes: tuple[ReleaseNote, ...],
    *,
    q: str = "",
    kind: str = "",
    since: str = "",
    until: str = "",
    limit: int = 75,
    offset: int = 0,
) -> tuple[tuple[ReleaseNote, ...], int]:
    query = q.strip().lower()
    wanted = kind.strip().lower()
    if wanted in {"", "all"}:
        wanted = ""
    since_day = published_day(since)
    until_day = published_day(until)
    matched: list[ReleaseNote] = []
    for note in notes:
        if wanted and note.kind != wanted:
            continue
        day = note.published_at[:10]
        if since_day and day < since_day:
            continue
        if until_day and day > until_day:
            continue
        if query:
            haystack = " ".join(
                (note.product, note.title, note.summary, note.release_note_type, note.kind)
            ).lower()
            if query not in haystack:
                continue
        matched.append(note)
    start = max(offset, 0)
    size = min(max(limit, 1), 200)
    return tuple(matched[start : start + size]), len(matched)


def normalize_note(row: Mapping[str, Any]) -> ReleaseNote | None:
    product = str(row.get("product_name") or "").strip()
    published = str(row.get("published_at") or "").strip()
    note_type = str(row.get("release_note_type") or "").strip()
    version = str(row.get("product_version_name") or "").strip()
    if not product or len(published) < 10:
        return None
    description = strip_html(str(row.get("description") or ""))
    summary = description[:SUMMARY_LIMIT].rstrip()
    if len(description) > SUMMARY_LIMIT:
        summary = summary.rsplit(" ", 1)[0] + "…"
    title = summary or f"{product}: {note_type or 'update'}"
    if len(title) > 140:
        title = title[:137].rsplit(" ", 1)[0] + "…"
    return ReleaseNote(
        id=_note_id(product, published, note_type, version, description),
        product=product,
        kind=note_kind(note_type),
        release_note_type=note_type or "OTHER",
        title=title,
        summary=summary,
        published_at=f"{published[:10]}T00:00:00Z",
        source_url=SOURCE_URL,
    )


def notes_to_changes(notes: tuple[ReleaseNote, ...]) -> list[dict[str, Any]]:
    return [
        {
            "id": note.id,
            "serviceId": note.product,
            "product": note.product,
            "title": note.title,
            "summary": note.summary,
            "kind": note.kind,
            "releaseNoteType": note.release_note_type,
            "status": "published",
            "effectiveAt": note.published_at,
            "retiredIdentifiers": [],
            "recommendedReplacement": None,
            "sourceUrl": note.source_url,
            "publishedAt": note.published_at,
        }
        for note in notes
    ]


def snapshot_to_payload(snapshot: ReleaseNotesSnapshot) -> dict[str, Any]:
    return {
        "trust": {
            "classification": "untrusted_provider_input",
            "note": "Release notes are changelog text, not a typed shutdown catalog.",
        },
        "source": snapshot.source,
        "fetched_at": snapshot.fetched_at,
        "window_days": snapshot.window_days,
        "changes": notes_to_changes(snapshot.notes),
    }


def load_google_release_notes(*, path: Path | None = None) -> ReleaseNotesSnapshot:
    snapshot = path or notes_path()
    try:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogUnavailableError("google release notes snapshot is missing") from exc
    except json.JSONDecodeError as exc:
        raise CatalogUnavailableError("google release notes snapshot is malformed") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("changes"), list):
        raise CatalogUnavailableError("google release notes snapshot is malformed")
    notes: list[ReleaseNote] = []
    for row in payload["changes"]:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        published = str(row.get("publishedAt") or row.get("effectiveAt") or "")
        if len(published) < 10:
            continue
        notes.append(
            ReleaseNote(
                id=str(row.get("id") or ""),
                product=str(row.get("product") or row.get("serviceId") or ""),
                kind=str(row.get("kind") or "other"),
                release_note_type=str(row.get("releaseNoteType") or ""),
                title=str(row.get("title") or ""),
                summary=str(row.get("summary") or ""),
                published_at=published,
                source_url=str(row.get("sourceUrl") or SOURCE_URL),
            )
        )
    return ReleaseNotesSnapshot(
        fetched_at=str(payload.get("fetched_at") or ""),
        window_days=int(payload.get("window_days") or WINDOW_DAYS),
        source=str(payload.get("source") or TABLE),
        notes=uniquify_note_ids(tuple(notes)),
    )


def _cell(row: Mapping[str, Any], index: int) -> str:
    fields = row.get("f")
    if not isinstance(fields, list) or index >= len(fields):
        return ""
    cell = fields[index]
    if not isinstance(cell, dict):
        return ""
    value = cell.get("v")
    return "" if value is None else str(value)


def _rows_from_bq(rows: list[Any]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed.append(
            {
                "published_at": _cell(row, 0),
                "product_name": _cell(row, 1),
                "release_note_type": _cell(row, 2),
                "product_version_name": _cell(row, 3),
                "description": _cell(row, 4),
            }
        )
    return parsed


async def _query_release_notes(
    client: httpx.AsyncClient,
    *,
    project: str,
    token: str,
    qualified_table: str = TABLE,
) -> list[dict[str, str]]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    start = await client.post(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/queries",
        headers=headers,
        json={
            "query": release_notes_query(qualified_table),
            "useLegacySql": False,
            "maxResults": PAGE_SIZE,
            "timeoutMs": QUERY_TIMEOUT_MS,
        },
    )
    if start.status_code >= 400:
        raise CatalogUnavailableError(f"BigQuery returned {start.status_code}")
    payload = start.json()
    if payload.get("jobComplete") is False:
        raise CatalogUnavailableError("BigQuery release notes query did not finish")
    rows = list(payload.get("rows") or [])
    page_token = str(payload.get("pageToken") or "")
    job = payload.get("jobReference") if isinstance(payload.get("jobReference"), dict) else {}
    job_id = str(job.get("jobId") or "")
    location = str(job.get("location") or "US")
    while page_token and job_id:
        more = await client.get(
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/queries/{job_id}",
            headers=headers,
            params={"pageToken": page_token, "maxResults": PAGE_SIZE, "location": location},
        )
        if more.status_code >= 400:
            raise CatalogUnavailableError(f"BigQuery returned {more.status_code}")
        page = more.json()
        rows.extend(page.get("rows") or [])
        page_token = str(page.get("pageToken") or "")
    return _rows_from_bq(rows)


def build_snapshot(
    rows: list[Mapping[str, Any]],
    *,
    fetched_at: str,
    source: str = TABLE,
) -> ReleaseNotesSnapshot:
    notes = uniquify_note_ids(
        tuple(note for note in (normalize_note(row) for row in rows) if note is not None)
    )
    return ReleaseNotesSnapshot(
        fetched_at=fetched_at,
        window_days=WINDOW_DAYS,
        source=source,
        notes=notes,
    )


async def fetch_release_notes(
    *,
    qualified_table: str = TABLE,
    environ: Mapping[str, str] | None = None,
    base_dir: Path | None = None,
    client: httpx.AsyncClient | None = None,
    now: float | None = None,
) -> ReleaseNotesSnapshot:
    """Query a release-notes table. Billing project is the service account."""
    clock = time.time() if now is None else now
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock))
    key_path = credentials_path(environ, base_dir=base_dir)
    billing_project = project_id(key_path, environ)
    token = await asyncio.to_thread(_mint_token, key_path)
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        rows = await _query_release_notes(
            http, project=billing_project, token=token, qualified_table=qualified_table
        )
    finally:
        if own_client:
            await http.aclose()
    return build_snapshot(rows, fetched_at=fetched_at, source=qualified_table)


async def refresh_google_release_notes(
    *,
    environ: Mapping[str, str] | None = None,
    base_dir: Path | None = None,
    client: httpx.AsyncClient | None = None,
    now: float | None = None,
    dest: Path | None = None,
    qualified_table: str = TABLE,
) -> ReleaseNotesSnapshot:
    """Query the public table. Persistence is Postgres, not `dest`."""
    del dest
    return await fetch_release_notes(
        qualified_table=qualified_table,
        environ=environ,
        base_dir=base_dir,
        client=client,
        now=now,
    )
