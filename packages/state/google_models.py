"""Gemini / Vertex model catalog and lifecycle snapshot.

Provider pages and list APIs are untrusted input. This module copies dates and
identifiers out of those documents; it does not invent a shutdown day, a
replacement model ID, or a launch stage. Serving reads the committed JSON.
Refresh re-fetches the pages and APIs to rewrite that file.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlparse

import httpx

from packages.state.gcp_catalog import (
    CatalogUnavailableError,
    _mint_token,
    credentials_path,
)

MODELS_FILENAME: Final[str] = "google_models.json"
GEMINI_DEPRECATIONS_URL: Final[str] = "https://ai.google.dev/gemini-api/docs/deprecations"
VERTEX_LIFECYCLE_URL: Final[str] = (
    "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions"
)
GEMINI_MODELS_URL: Final[str] = "https://generativelanguage.googleapis.com/v1beta/models"
VERTEX_MODELS_URLS: Final[tuple[str, ...]] = (
    "https://aiplatform.googleapis.com/v1beta1/publishers/google/models",
    "https://us-central1-aiplatform.googleapis.com/v1beta1/publishers/google/models",
)
DEFAULT_GEMINI_KEY_FILE: Final[str] = ".secrets/gemini_api_key.txt"
REQUEST_TIMEOUT_SECONDS: Final[float] = 45.0
PAGE_SIZE: Final[int] = 100

_MONTHS: Final[dict[str, int]] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_NO_DATE: Final[frozenset[str]] = frozenset(
    {
        "",
        "no shutdown date announced",
        "no retirement date announced",
    }
)
_SECTION_ROW: Final[re.Pattern[str]] = re.compile(r"^(preview models|retired models)$", re.I)
_MODEL_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:gemini|imagen|veo|lyria|gemma)(?:-[a-zA-Z0-9._@-]+)|"
    r"(?:text-embedding|text-multilingual-embedding|multimodalembedding|"
    r"embedding|textembedding-gecko)(?:-[a-zA-Z0-9._@-]+|@[a-zA-Z0-9._-]+)|"
    r"(?:text-bison|chat-bison|code-gecko|imagetext)(?:@[a-zA-Z0-9._-]+)?",
    re.I,
)


@dataclass(frozen=True)
class LifecycleRow:
    model_id: str
    surface: str
    family: str
    release_date: str | None
    release_date_raw: str
    shutdown_date: str | None
    shutdown_date_raw: str
    shutdown_qualifier: str | None
    replacement: str | None
    replacement_raw: str
    source_url: str
    preview_section: bool


@dataclass(frozen=True)
class ModelRecord:
    id: str
    name: str
    display_name: str
    surface: str
    family: str
    status: str
    launch_stage: str | None
    version_state: str | None
    version: str | None
    release_date: str | None
    release_date_raw: str
    shutdown_date: str | None
    shutdown_date_raw: str
    shutdown_qualifier: str | None
    replacement: str | None
    replacement_raw: str
    summary: str
    identifiers: tuple[str, ...]
    docs_url: str


@dataclass(frozen=True)
class ModelChange:
    id: str
    service_id: str
    title: str
    kind: str
    status: str
    effective_at: str
    retired_identifiers: tuple[str, ...]
    recommended_replacement: str | None
    source_url: str
    published_at: str


@dataclass(frozen=True)
class GoogleModelsSnapshot:
    fetched_at: str
    sources: tuple[dict[str, Any], ...]
    models: tuple[ModelRecord, ...]
    changes: tuple[ModelChange, ...]


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._parts is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._parts)).strip())
            self._parts = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(cell for cell in self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)


def models_path(*, base_dir: Path | None = None) -> Path:
    root = Path(__file__).resolve().parent if base_dir is None else base_dir
    return root / "data" / MODELS_FILENAME


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def classify_family(model_id: str) -> str:
    lowered = model_id.lower()
    if lowered.startswith("imagen") or lowered == "imagetext":
        return "imagen"
    if lowered.startswith("veo"):
        return "veo"
    if lowered.startswith("lyria"):
        return "lyria"
    if "embed" in lowered:
        return "embedding"
    if lowered.startswith("gemma"):
        return "gemma"
    if "robotics" in lowered:
        return "robotics"
    if lowered.startswith("gemini") or "live" in lowered:
        return "gemini"
    return "other"


def parse_provider_date(raw: str) -> tuple[str | None, str | None]:
    """Parse a provider date. Month-only stays YYYY-MM; a missing day is not invented."""
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if text.lower() in _NO_DATE:
        return None, None
    qualifier: str | None = None
    lowered = text.lower()
    if lowered.endswith(" or later"):
        qualifier = "or_later"
        text = text[: -len(" or later")]
    elif lowered.startswith("no sooner than "):
        qualifier = "no_sooner_than"
        text = text[len("no sooner than ") :]
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", text)
    if match:
        month = _MONTHS.get(match.group(1).lower())
        if month:
            return f"{match.group(3)}-{month:02d}-{int(match.group(2)):02d}", qualifier
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", text)
    if match:
        month = _MONTHS.get(match.group(1).lower())
        if month:
            return f"{match.group(2)}-{month:02d}", qualifier
    return None, qualifier


def extract_model_id(raw: str) -> str | None:
    text = (raw or "").strip().strip("`")
    if not text:
        return None
    match = _MODEL_ID_RE.search(text)
    if not match:
        return None
    value = match.group(0).rstrip(".,);")
    # Some docs pages glue the next word onto the identifier (`previewor`).
    if value.lower().endswith("or"):
        trimmed = value[:-2]
        if _MODEL_ID_RE.fullmatch(trimmed):
            value = trimmed
    return value


def infer_status(
    *,
    model_id: str,
    launch_stage: str | None,
    shutdown_date: str | None,
    preview_section: bool,
    today: date,
) -> str:
    if shutdown_date and len(shutdown_date) == 10:
        if date.fromisoformat(shutdown_date) < today:
            return "retired"
    stage = (launch_stage or "").upper()
    if stage in {"PUBLIC_PREVIEW", "PRIVATE_PREVIEW", "EXPERIMENTAL"}:
        return "preview"
    lowered = model_id.lower()
    if preview_section or "-preview" in lowered or "-exp" in lowered or lowered.endswith("-eap"):
        return "preview"
    return "live"


def parse_lifecycle_tables(html: str, *, surface: str, source_url: str) -> tuple[LifecycleRow, ...]:
    parser = _TableParser()
    parser.feed(html)
    rows: list[LifecycleRow] = []
    seen: set[str] = set()
    for table in parser.tables:
        if not table or len(table[0]) < 3:
            continue
        header = [cell.lower() for cell in table[0]]
        if "model" not in header[0]:
            continue
        in_preview = False
        for cells in table[1:]:
            model_raw = cells[0] if cells else ""
            if _SECTION_ROW.match(model_raw.strip()):
                in_preview = "preview" in model_raw.lower()
                continue
            model_id = extract_model_id(model_raw) or model_raw.strip().strip("`")
            if not model_id or " " in model_id:
                continue
            release_raw = cells[1] if len(cells) > 1 else ""
            shutdown_raw = cells[2] if len(cells) > 2 else ""
            replacement_raw = cells[3] if len(cells) > 3 else ""
            release_date, _ = parse_provider_date(release_raw)
            shutdown_date, qualifier = parse_provider_date(shutdown_raw)
            key = f"{surface}:{model_id}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                LifecycleRow(
                    model_id=model_id,
                    surface=surface,
                    family=classify_family(model_id),
                    release_date=release_date,
                    release_date_raw=release_raw,
                    shutdown_date=shutdown_date,
                    shutdown_date_raw=shutdown_raw,
                    shutdown_qualifier=qualifier,
                    replacement=extract_model_id(replacement_raw),
                    replacement_raw=replacement_raw,
                    source_url=source_url,
                    preview_section=in_preview,
                )
            )
    return tuple(rows)


def _strip_model_name(name: str) -> str:
    value = name.strip()
    if "/models/" in value:
        return value.rsplit("/models/", 1)[-1]
    if value.startswith("models/"):
        return value.removeprefix("models/")
    return value


def _gemini_key(environ: Mapping[str, str] | None, base_dir: Path | None) -> str:
    env = os.environ if environ is None else environ
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        value = env.get(name, "").strip()
        if value:
            return value
    root = _repo_root() if base_dir is None else base_dir
    path = root / DEFAULT_GEMINI_KEY_FILE
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    raise CatalogUnavailableError("Gemini API key is not configured")


def _docs_url(surface: str, model_id: str) -> str:
    if surface == "gemini_api":
        return "https://ai.google.dev/gemini-api/docs/models"
    return VERTEX_LIFECYCLE_URL


def _service_id(surface: str) -> str:
    if surface == "gemini_api":
        return "generativelanguage.googleapis.com"
    return "aiplatform.googleapis.com"


def _iso_midnight(value: str) -> str | None:
    if len(value) == 10:
        return f"{value}T00:00:00Z"
    return None


def _lifecycle_map(rows: tuple[LifecycleRow, ...]) -> dict[tuple[str, str], LifecycleRow]:
    return {(row.surface, row.model_id): row for row in rows}


def _lifecycle_by_id(rows: tuple[LifecycleRow, ...]) -> dict[str, LifecycleRow]:
    by_id: dict[str, LifecycleRow] = {}
    for row in rows:
        by_id.setdefault(row.model_id, row)
    return by_id


def _record_from_lifecycle(row: LifecycleRow, *, today: date) -> ModelRecord:
    return ModelRecord(
        id=row.model_id,
        name=row.model_id,
        display_name=row.model_id,
        surface=row.surface,
        family=row.family,
        status=infer_status(
            model_id=row.model_id,
            launch_stage=None,
            shutdown_date=row.shutdown_date,
            preview_section=row.preview_section,
            today=today,
        ),
        launch_stage=None,
        version_state=None,
        version=None,
        release_date=row.release_date,
        release_date_raw=row.release_date_raw,
        shutdown_date=row.shutdown_date,
        shutdown_date_raw=row.shutdown_date_raw,
        shutdown_qualifier=row.shutdown_qualifier,
        replacement=row.replacement,
        replacement_raw=row.replacement_raw,
        summary="",
        identifiers=(row.model_id,),
        docs_url=row.source_url,
    )


def _apply_lifecycle(record: ModelRecord, row: LifecycleRow | None, *, today: date) -> ModelRecord:
    if row is None:
        return record
    return ModelRecord(
        id=record.id,
        name=record.name,
        display_name=record.display_name,
        surface=record.surface,
        family=record.family or row.family,
        status=infer_status(
            model_id=record.id,
            launch_stage=record.launch_stage,
            shutdown_date=row.shutdown_date,
            preview_section=row.preview_section,
            today=today,
        ),
        launch_stage=record.launch_stage,
        version_state=record.version_state,
        version=record.version,
        release_date=row.release_date or record.release_date,
        release_date_raw=row.release_date_raw or record.release_date_raw,
        shutdown_date=row.shutdown_date,
        shutdown_date_raw=row.shutdown_date_raw,
        shutdown_qualifier=row.shutdown_qualifier,
        replacement=row.replacement,
        replacement_raw=row.replacement_raw,
        summary=record.summary,
        identifiers=record.identifiers,
        docs_url=row.source_url or record.docs_url,
    )


def normalize_gemini_model(raw: Mapping[str, Any], *, today: date) -> ModelRecord | None:
    name = str(raw.get("name") or "").strip()
    model_id = _strip_model_name(name)
    if not model_id:
        return None
    display = str(raw.get("displayName") or model_id).strip()
    return ModelRecord(
        id=model_id,
        name=model_id,
        display_name=display,
        surface="gemini_api",
        family=classify_family(model_id),
        status=infer_status(
            model_id=model_id,
            launch_stage=None,
            shutdown_date=None,
            preview_section=False,
            today=today,
        ),
        launch_stage=None,
        version_state=None,
        version=str(raw.get("version") or "") or None,
        release_date=None,
        release_date_raw="",
        shutdown_date=None,
        shutdown_date_raw="",
        shutdown_qualifier=None,
        replacement=None,
        replacement_raw="",
        summary=str(raw.get("description") or "").strip(),
        identifiers=(model_id, name) if name != model_id else (model_id,),
        docs_url=_docs_url("gemini_api", model_id),
    )


def normalize_vertex_model(raw: Mapping[str, Any], *, today: date) -> ModelRecord | None:
    name = str(raw.get("name") or "").strip()
    model_id = _strip_model_name(name)
    if not model_id:
        return None
    launch_stage = str(raw.get("launchStage") or "") or None
    version_state = str(raw.get("versionState") or "") or None
    return ModelRecord(
        id=model_id,
        name=model_id,
        display_name=model_id,
        surface="vertex",
        family=classify_family(model_id),
        status=infer_status(
            model_id=model_id,
            launch_stage=launch_stage,
            shutdown_date=None,
            preview_section=False,
            today=today,
        ),
        launch_stage=launch_stage,
        version_state=version_state,
        version=str(raw.get("versionId") or "") or None,
        release_date=None,
        release_date_raw="",
        shutdown_date=None,
        shutdown_date_raw="",
        shutdown_qualifier=None,
        replacement=None,
        replacement_raw="",
        summary="",
        identifiers=(model_id, name) if name != model_id else (model_id,),
        docs_url=_docs_url("vertex", model_id),
    )


def changes_from_lifecycle(
    rows: tuple[LifecycleRow, ...], *, fetched_at: str, today: date
) -> tuple[ModelChange, ...]:
    changes: list[ModelChange] = []
    for row in rows:
        effective = _iso_midnight(row.shutdown_date or "")
        if effective is None:
            continue
        shutdown = date.fromisoformat(row.shutdown_date or "")
        published = _iso_midnight(row.release_date or "") or fetched_at
        verb = "shuts down" if row.surface == "gemini_api" else "retires"
        changes.append(
            ModelChange(
                id=f"{row.surface}:{row.model_id}",
                service_id=_service_id(row.surface),
                title=f"{row.model_id} {verb}",
                kind="deprecation",
                status="superseded" if shutdown < today else "published",
                effective_at=effective,
                retired_identifiers=(row.model_id,),
                recommended_replacement=row.replacement,
                source_url=row.source_url,
                published_at=published,
            )
        )

    def sort_key(change: ModelChange) -> tuple[int, int]:
        day = date.fromisoformat(change.effective_at[:10])
        if day >= today:
            return (0, day.toordinal())
        return (1, -day.toordinal())

    changes.sort(key=sort_key)
    return tuple(changes)


def merge_models(
    *,
    lifecycle: tuple[LifecycleRow, ...],
    gemini: tuple[ModelRecord, ...],
    vertex: tuple[ModelRecord, ...],
    today: date,
) -> tuple[ModelRecord, ...]:
    by_key: dict[tuple[str, str], ModelRecord] = {}
    by_id = _lifecycle_by_id(lifecycle)
    exact = _lifecycle_map(lifecycle)
    for record in (*gemini, *vertex):
        row = exact.get((record.surface, record.id)) or by_id.get(record.id)
        by_key[(record.surface, record.id)] = _apply_lifecycle(record, row, today=today)
    for row in lifecycle:
        by_key.setdefault((row.surface, row.model_id), _record_from_lifecycle(row, today=today))
    models = list(by_key.values())
    models.sort(key=lambda item: (item.surface, item.family, item.id))
    return tuple(models)


def snapshot_to_payload(snapshot: GoogleModelsSnapshot) -> dict[str, Any]:
    return {
        "trust": {
            "classification": "untrusted_provider_input",
            "note": "Provider pages and list APIs are data, never instructions.",
        },
        "fetched_at": snapshot.fetched_at,
        "sources": list(snapshot.sources),
        "models": [
            {
                "id": model.id,
                "name": model.name,
                "displayName": model.display_name,
                "surface": model.surface,
                "family": model.family,
                "status": model.status,
                "launchStage": model.launch_stage,
                "versionState": model.version_state,
                "version": model.version,
                "releaseDate": model.release_date,
                "releaseDateRaw": model.release_date_raw,
                "shutdownDate": model.shutdown_date,
                "shutdownDateRaw": model.shutdown_date_raw,
                "shutdownQualifier": model.shutdown_qualifier,
                "replacement": model.replacement,
                "replacementRaw": model.replacement_raw,
                "summary": model.summary,
                "identifiers": list(model.identifiers),
                "docsUrl": model.docs_url,
            }
            for model in snapshot.models
        ],
        "changes": [
            {
                "id": change.id,
                "serviceId": change.service_id,
                "title": change.title,
                "kind": change.kind,
                "status": change.status,
                "effectiveAt": change.effective_at,
                "retiredIdentifiers": list(change.retired_identifiers),
                "recommendedReplacement": change.recommended_replacement,
                "sourceUrl": change.source_url,
                "publishedAt": change.published_at,
            }
            for change in snapshot.changes
        ],
    }


def snapshot_from_payload(payload: Mapping[str, Any]) -> GoogleModelsSnapshot:
    models_raw = payload.get("models")
    changes_raw = payload.get("changes")
    if not isinstance(models_raw, list) or not isinstance(changes_raw, list):
        raise CatalogUnavailableError("google models snapshot is malformed")
    models: list[ModelRecord] = []
    for row in models_raw:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        identifiers = row.get("identifiers")
        models.append(
            ModelRecord(
                id=str(row.get("id") or ""),
                name=str(row.get("name") or row.get("id") or ""),
                display_name=str(row.get("displayName") or row.get("id") or ""),
                surface=str(row.get("surface") or ""),
                family=str(row.get("family") or "other"),
                status=str(row.get("status") or "live"),
                launch_stage=str(row["launchStage"]) if row.get("launchStage") else None,
                version_state=str(row["versionState"]) if row.get("versionState") else None,
                version=str(row["version"]) if row.get("version") else None,
                release_date=str(row["releaseDate"]) if row.get("releaseDate") else None,
                release_date_raw=str(row.get("releaseDateRaw") or ""),
                shutdown_date=str(row["shutdownDate"]) if row.get("shutdownDate") else None,
                shutdown_date_raw=str(row.get("shutdownDateRaw") or ""),
                shutdown_qualifier=str(row["shutdownQualifier"])
                if row.get("shutdownQualifier")
                else None,
                replacement=str(row["replacement"]) if row.get("replacement") else None,
                replacement_raw=str(row.get("replacementRaw") or ""),
                summary=str(row.get("summary") or ""),
                identifiers=tuple(str(item) for item in identifiers)
                if isinstance(identifiers, list)
                else (str(row.get("id") or ""),),
                docs_url=str(row.get("docsUrl") or ""),
            )
        )
    changes: list[ModelChange] = []
    for row in changes_raw:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        retired = row.get("retiredIdentifiers")
        changes.append(
            ModelChange(
                id=str(row.get("id") or ""),
                service_id=str(row.get("serviceId") or ""),
                title=str(row.get("title") or ""),
                kind=str(row.get("kind") or "deprecation"),
                status=str(row.get("status") or "published"),
                effective_at=str(row.get("effectiveAt") or ""),
                retired_identifiers=tuple(str(item) for item in retired)
                if isinstance(retired, list)
                else (),
                recommended_replacement=str(row["recommendedReplacement"])
                if row.get("recommendedReplacement")
                else None,
                source_url=str(row.get("sourceUrl") or ""),
                published_at=str(row.get("publishedAt") or ""),
            )
        )
    sources = payload.get("sources")
    return GoogleModelsSnapshot(
        fetched_at=str(payload.get("fetched_at") or ""),
        sources=tuple(item for item in sources if isinstance(item, dict))
        if isinstance(sources, list)
        else (),
        models=tuple(models),
        changes=tuple(change for change in changes if change.effective_at),
    )


def load_google_models(*, path: Path | None = None) -> GoogleModelsSnapshot:
    snapshot = path or models_path()
    try:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogUnavailableError("google models snapshot is missing") from exc
    except json.JSONDecodeError as exc:
        raise CatalogUnavailableError("google models snapshot is malformed") from exc
    if not isinstance(payload, dict):
        raise CatalogUnavailableError("google models snapshot is malformed")
    return snapshot_from_payload(payload)


async def _get_text(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(
        url,
        headers={"User-Agent": "PatchAPI-catalog-refresh/0.1", "Accept": "text/html"},
        follow_redirects=True,
    )
    if response.status_code >= 400:
        raise CatalogUnavailableError(f"{urlparse(url).netloc} returned {response.status_code}")
    return response.text


async def _list_gemini(
    client: httpx.AsyncClient, key: str
) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, str | int] = {"key": key, "pageSize": PAGE_SIZE}
        if page_token:
            params["pageToken"] = page_token
        response = await client.get(GEMINI_MODELS_URL, params=params)
        if response.status_code >= 400:
            raise CatalogUnavailableError(f"Gemini models.list returned {response.status_code}")
        payload = response.json()
        batch = payload.get("models")
        if isinstance(batch, list):
            models.extend(item for item in batch if isinstance(item, dict))
        page_token = str(payload.get("nextPageToken") or "")
        if not page_token:
            break
    return models


async def _list_vertex(
    client: httpx.AsyncClient, token: str
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    models: list[dict[str, Any]] = []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    for url in VERTEX_MODELS_URLS:
        page_token = ""
        while True:
            params: dict[str, str | int] = {"pageSize": PAGE_SIZE}
            if page_token:
                params["pageToken"] = page_token
            response = await client.get(url, headers=headers, params=params)
            if response.status_code >= 400:
                raise CatalogUnavailableError(
                    f"Vertex publishers.models.list returned {response.status_code}"
                )
            payload = response.json()
            batch = payload.get("publisherModels") or payload.get("models")
            if isinstance(batch, list):
                for item in batch:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "")
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    models.append(item)
            page_token = str(payload.get("nextPageToken") or "")
            if not page_token:
                break
    return models


def build_snapshot(
    *,
    gemini_html: str,
    vertex_html: str,
    gemini_raw: list[Mapping[str, Any]],
    vertex_raw: list[Mapping[str, Any]],
    fetched_at: str,
    today: date,
    sources: tuple[dict[str, Any], ...],
) -> GoogleModelsSnapshot:
    gemini_rows = parse_lifecycle_tables(
        gemini_html, surface="gemini_api", source_url=GEMINI_DEPRECATIONS_URL
    )
    vertex_rows = parse_lifecycle_tables(
        vertex_html, surface="vertex", source_url=VERTEX_LIFECYCLE_URL
    )
    lifecycle = gemini_rows + vertex_rows
    gemini_models = tuple(
        record
        for record in (normalize_gemini_model(row, today=today) for row in gemini_raw)
        if record is not None
    )
    vertex_models = tuple(
        record
        for record in (normalize_vertex_model(row, today=today) for row in vertex_raw)
        if record is not None
    )
    models = merge_models(
        lifecycle=lifecycle, gemini=gemini_models, vertex=vertex_models, today=today
    )
    return GoogleModelsSnapshot(
        fetched_at=fetched_at,
        sources=sources,
        models=models,
        changes=changes_from_lifecycle(lifecycle, fetched_at=fetched_at, today=today),
    )


async def refresh_google_models(
    *,
    environ: Mapping[str, str] | None = None,
    base_dir: Path | None = None,
    client: httpx.AsyncClient | None = None,
    now: float | None = None,
    dest: Path | None = None,
) -> GoogleModelsSnapshot:
    """Fetch official pages and list APIs, then rewrite the committed snapshot."""
    clock = time.time() if now is None else now
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock))
    today = datetime.fromtimestamp(clock, tz=UTC).date()
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    sources: list[dict[str, Any]] = []
    gemini_html = ""
    vertex_html = ""
    gemini_raw: list[dict[str, Any]] = []
    vertex_raw: list[dict[str, Any]] = []
    try:
        gemini_html = await _get_text(http, GEMINI_DEPRECATIONS_URL)
        sources.append(
            {"id": "gemini_deprecations", "url": GEMINI_DEPRECATIONS_URL, "kind": "html_table"}
        )
        vertex_html = await _get_text(http, VERTEX_LIFECYCLE_URL)
        sources.append(
            {"id": "vertex_lifecycle", "url": VERTEX_LIFECYCLE_URL, "kind": "html_table"}
        )
        try:
            key = _gemini_key(environ, base_dir)
            gemini_raw = await _list_gemini(http, key)
            sources.append({"id": "gemini_models_list", "url": GEMINI_MODELS_URL, "kind": "api"})
        except CatalogUnavailableError:
            sources.append(
                {
                    "id": "gemini_models_list",
                    "url": GEMINI_MODELS_URL,
                    "kind": "api",
                    "skipped": "key missing or list failed",
                }
            )
        try:
            token = await asyncio.to_thread(
                _mint_token, credentials_path(environ, base_dir=base_dir)
            )
            vertex_raw = await _list_vertex(http, token)
            sources.append(
                {
                    "id": "vertex_publisher_models",
                    "url": VERTEX_MODELS_URLS[0],
                    "kind": "api",
                }
            )
        except CatalogUnavailableError:
            sources.append(
                {
                    "id": "vertex_publisher_models",
                    "url": VERTEX_MODELS_URLS[0],
                    "kind": "api",
                    "skipped": "credentials missing or list failed",
                }
            )
    finally:
        if own_client:
            await http.aclose()
    if not gemini_html or not vertex_html:
        raise CatalogUnavailableError("model lifecycle pages could not be retrieved")
    snapshot = build_snapshot(
        gemini_html=gemini_html,
        vertex_html=vertex_html,
        gemini_raw=gemini_raw,
        vertex_raw=vertex_raw,
        fetched_at=fetched_at,
        today=today,
        sources=tuple(sources),
    )
    target = dest or models_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot_to_payload(snapshot), indent=2) + "\n", encoding="utf-8")
    return snapshot
