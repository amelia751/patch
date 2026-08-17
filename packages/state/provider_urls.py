"""Parse the one URL a human pastes onto a provider connection.

Project, dataset, and table are derived here. The client does not send them.
An unrecognized shape is an error, not a guessed adapter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, unquote, urlparse

ConnectionKind = Literal["catalog", "changes"]
AdapterName = Literal["service_usage", "bigquery_release_notes"]

# GCP project id, or a numeric project number. Do not invent a default.
_PROJECT = re.compile(r"^(?:[a-z][a-z0-9-]{4,28}[a-z0-9]|[0-9]{6,30})$")
_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
_SERVICE_USAGE = re.compile(
    r"^/v1/projects/(?P<project>[^/]+)/services/?$",
    re.IGNORECASE,
)
_BQ_REST = re.compile(
    r"^/bigquery/v2/projects/(?P<project>[^/]+)/datasets/(?P<dataset>[^/]+)/tables/(?P<table>[^/]+)/?$",
    re.IGNORECASE,
)
_DOTTED = re.compile(
    r"^(?P<project>[A-Za-z0-9-]+)\.(?P<dataset>[A-Za-z0-9_]+)\.(?P<table>[A-Za-z0-9_]+)$"
)


class UnsupportedProviderUrl(ValueError):
    """The pasted link does not match a supported ingest adapter."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ParsedProviderUrl:
    kind: ConnectionKind
    adapter: AdapterName
    source_url: str
    canonical_url: str
    parsed: dict[str, str]


def parse_provider_url(kind: ConnectionKind, url: str) -> ParsedProviderUrl:
    """Return the adapter and derived fields, or raise UnsupportedProviderUrl."""
    raw = (url or "").strip()
    if not raw:
        raise UnsupportedProviderUrl(
            f"unsupported_{kind}_url",
            "Paste a catalog or changes endpoint.",
        )
    if kind == "catalog":
        return _parse_catalog(raw)
    if kind == "changes":
        return _parse_changes(raw)
    raise UnsupportedProviderUrl("unsupported_connection_kind", "Unknown connection kind.")


def _require_project(value: str) -> str:
    project = unquote(value).strip()
    if not _PROJECT.fullmatch(project):
        raise UnsupportedProviderUrl(
            "unsupported_catalog_url",
            "Could not read a Service Usage project from that link.",
        )
    return project


def _require_ident(value: str, *, field: str) -> str:
    ident = unquote(value).strip()
    if not _IDENT.fullmatch(ident):
        raise UnsupportedProviderUrl(
            "unsupported_changes_url",
            f"Could not read a BigQuery {field} from that link.",
        )
    return ident


def _parse_catalog(raw: str) -> ParsedProviderUrl:
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host != "serviceusage.googleapis.com":
        raise UnsupportedProviderUrl(
            "unsupported_catalog_url",
            "Could not read a Service Usage project from that link.",
        )
    match = _SERVICE_USAGE.fullmatch(parsed.path or "")
    if match is None:
        raise UnsupportedProviderUrl(
            "unsupported_catalog_url",
            "Could not read a Service Usage project from that link.",
        )
    project = _require_project(match.group("project"))
    canonical = f"https://serviceusage.googleapis.com/v1/projects/{project}/services"
    return ParsedProviderUrl(
        kind="catalog",
        adapter="service_usage",
        source_url=raw,
        canonical_url=canonical,
        parsed={"project": project},
    )


def _ws_parts(ws: str) -> dict[str, str] | None:
    """Cloud Console `ws` embeds project/dataset/table as !1s !2s !3s."""
    tokens = [part for part in ws.split("!") if part]
    found: dict[str, str] = {}
    for token in tokens:
        if len(token) < 3 or token[1] != "s":
            continue
        key = {"1": "project", "2": "dataset", "3": "table"}.get(token[0])
        if key:
            found[key] = token[2:]
    if {"project", "dataset", "table"} <= found.keys():
        return found
    return None


def _parse_changes(raw: str) -> ParsedProviderUrl:
    dotted = _DOTTED.fullmatch(raw)
    if dotted:
        return _changes_result(
            raw,
            project=dotted.group("project"),
            dataset=dotted.group("dataset"),
            table=dotted.group("table"),
        )

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query)

    if host == "bigquery.googleapis.com":
        match = _BQ_REST.fullmatch(parsed.path or "")
        if match is None:
            raise UnsupportedProviderUrl(
                "unsupported_changes_url",
                "Could not read a BigQuery table from that link.",
            )
        return _changes_result(
            raw,
            project=match.group("project"),
            dataset=match.group("dataset"),
            table=match.group("table"),
        )

    if host == "console.cloud.google.com" and "/bigquery" in (parsed.path or ""):
        project = (query.get("p") or query.get("project") or [""])[0]
        dataset = (query.get("d") or [""])[0]
        table = (query.get("t") or [""])[0]
        if not (project and dataset and table):
            ws = (query.get("ws") or [""])[0]
            parts = _ws_parts(ws) if ws else None
            if parts is None:
                raise UnsupportedProviderUrl(
                    "unsupported_changes_url",
                    "Could not read a BigQuery table from that link.",
                )
            project, dataset, table = parts["project"], parts["dataset"], parts["table"]
        return _changes_result(raw, project=project, dataset=dataset, table=table)

    raise UnsupportedProviderUrl(
        "unsupported_changes_url",
        "Could not read a BigQuery table from that link.",
    )


def _changes_result(
    raw: str, *, project: str, dataset: str, table: str
) -> ParsedProviderUrl:
    project_id = _require_project(project) if _PROJECT.fullmatch(unquote(project).strip()) else None
    if project_id is None:
        # Public datasets use project ids that still match _PROJECT; fail closed.
        raise UnsupportedProviderUrl(
            "unsupported_changes_url",
            "Could not read a BigQuery project from that link.",
        )
    dataset_id = _require_ident(dataset, field="dataset")
    table_id = _require_ident(table, field="table")
    qualified = f"{project_id}.{dataset_id}.{table_id}"
    return ParsedProviderUrl(
        kind="changes",
        adapter="bigquery_release_notes",
        source_url=raw,
        canonical_url=qualified,
        parsed={"project": project_id, "dataset": dataset_id, "table": table_id},
    )
