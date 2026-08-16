"""Google Cloud API catalog snapshot.

`GET /api/providers/google` reads `data/google_services.json`. That file is the
stand-in for the catalog table we will move to Postgres. Live Service Usage is
only used to regenerate the snapshot (`refresh_google_catalog`); a page load
never calls Google.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import httpx

from packages.auth.config import ADMIN_SCOPES, ENV_CREDENTIALS, ENV_PROJECT

DEFAULT_CREDENTIALS_FILE: Final[str] = ".secrets/gcp-service-account.json"
SERVICE_USAGE_URL: Final[str] = "https://serviceusage.googleapis.com/v1/projects/{project}/services"
PAGE_SIZE: Final[int] = 200
REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0
# list_available_requests defaults to 1 QPS. Bursting pages 429s the catalog.
PAGE_PAUSE_SECONDS: Final[float] = 1.1
RATE_LIMIT_RETRIES: Final[int] = 5

# First-party Google APIs end in this suffix. Marketplace listings use
# `*.endpoints.*.cloud.goog` and are not a provider catalog.
FIRST_PARTY_SUFFIX: Final[str] = ".googleapis.com"

_GROUP_RULES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "ai",
        (
            "aiplatform",
            "generativelanguage",
            "ml.",
            "automl",
            "vision",
            "speech",
            "translate",
            "dialogflow",
            "notebooks",
            "vertex",
            "gemini",
            "documentai",
            "recommendationengine",
            "discoveryengine",
            "retail",
        ),
    ),
    ("storage", ("storage", "filestore", "backupdr", "transfer")),
    (
        "compute",
        (
            "compute",
            "run.",
            "appengine",
            "cloudfunctions",
            "container",
            "batch.",
            "workstations",
            "apphub",
        ),
    ),
    (
        "database",
        (
            "sqladmin",
            "sql-component",
            "spanner",
            "bigtable",
            "firestore",
            "datastore",
            "redis",
            "memcache",
            "alloydb",
            "bigquery",
            "dataform",
        ),
    ),
    (
        "networking",
        (
            "dns.",
            "network",
            "servicenetworking",
            "vpcaccess",
            "certificatemanager",
            "trafficdirector",
            "networkconnectivity",
        ),
    ),
    (
        "security",
        (
            "iam.",
            "iamcredentials",
            "secretmanager",
            "cloudkms",
            "sts.",
            "iap.",
            "binaryauthorization",
            "websecurity",
            "recaptcha",
            "accesscontextmanager",
        ),
    ),
)


class CatalogUnavailableError(RuntimeError):
    """The catalog could not be loaded. The message is safe to show."""


@dataclass(frozen=True)
class CatalogService:
    id: str
    name: str
    slug: str
    product: str
    group: str
    summary: str
    status: str
    identifiers: tuple[str, ...]
    docs_url: str


@dataclass(frozen=True)
class GoogleCatalog:
    project: str
    fetched_at: str
    source: str
    services: tuple[CatalogService, ...]


CATALOG_FILENAME: Final[str] = "google_services.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def catalog_path(*, base_dir: Path | None = None) -> Path:
    """Committed snapshot. Postgres replaces this file later."""
    root = Path(__file__).resolve().parent if base_dir is None else base_dir
    return root / "data" / CATALOG_FILENAME


def credentials_path(
    environ: Mapping[str, str] | None = None, *, base_dir: Path | None = None
) -> Path:
    """Resolve the service-account file without reading it."""
    env = os.environ if environ is None else environ
    root = _repo_root() if base_dir is None else base_dir
    raw = env.get(ENV_CREDENTIALS, "").strip() or DEFAULT_CREDENTIALS_FILE
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else (root / candidate)


def project_id(key_path: Path, environ: Mapping[str, str] | None = None) -> str:
    """Return the GCP project, never any other field from the key file."""
    env = os.environ if environ is None else environ
    from_env = env.get(ENV_PROJECT, "").strip()
    if from_env:
        return from_env
    try:
        payload = json.loads(key_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogUnavailableError("service-account file is unreadable") from exc
    value = payload.get("project_id") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise CatalogUnavailableError("service-account file has no project_id")
    return value.strip()


def classify_group(api_name: str, title: str) -> str:
    """Map an API name/title onto a resources-tab category."""
    haystack = f"{api_name} {title}".lower()
    for group, needles in _GROUP_RULES:
        if any(needle in haystack for needle in needles):
            return group
    return "api"


def is_first_party(api_name: str) -> bool:
    return api_name.endswith(FIRST_PARTY_SUFFIX) and ".endpoints." not in api_name


def _slug(api_name: str) -> str:
    host = api_name.removesuffix(FIRST_PARTY_SUFFIX)
    return host.replace(".", "-")[:48] or "api"


# Service Usage titles are enable-an-API labels ("AlloyDB API"), not product
# names. Strip that catalog suffix. Leave "API" when it is part of the name
# ("API Discovery Service", "Content API for Shopping", "Google Cloud APIs").
_API_BEFORE_QUALIFIER: Final[re.Pattern[str]] = re.compile(
    r"\s+API(?=\s+(?:\(|v\d+\b|II\b|III\b|with\b))",
    re.IGNORECASE,
)


def display_name(title: str) -> str:
    """Product name for the UI. Does not invent a shorter marketing name."""
    text = re.sub(r"\s+", " ", title).strip()
    if text.upper().endswith(" API"):
        text = text[:-4].rstrip()
    else:
        text = _API_BEFORE_QUALIFIER.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text or title.strip()


def _product(title: str) -> str:
    return display_name(title)


def _documentation_summary(config: Mapping[str, Any], api_name: str) -> str:
    documentation = config.get("documentation")
    if isinstance(documentation, dict):
        text = str(documentation.get("summary") or "").strip()
        if text:
            return text
    if isinstance(documentation, str) and documentation.strip():
        return documentation.strip()
    return f"Google Cloud service {api_name}"


def normalize_service(raw: Mapping[str, Any]) -> CatalogService | None:
    config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
    api_name = str(config.get("name") or "").strip()
    if not api_name and isinstance(raw.get("name"), str):
        api_name = raw["name"].rsplit("/", 1)[-1].strip()
    if not is_first_party(api_name):
        return None
    title = str(config.get("title") or api_name).strip()
    product = display_name(title)
    return CatalogService(
        id=api_name,
        name=product,
        slug=_slug(api_name),
        product=product,
        group=classify_group(api_name, title),
        summary=_documentation_summary(config, api_name),
        status="live",
        identifiers=(api_name,),
        docs_url=f"https://console.cloud.google.com/apis/library/{api_name}",
    )


def _mint_token(key_path: Path) -> str:
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise CatalogUnavailableError("google-auth is not installed") from exc
    if not key_path.is_file():
        raise CatalogUnavailableError("Google Cloud credentials are not configured")
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(key_path), scopes=list(ADMIN_SCOPES)
        )
        credentials.refresh(google.auth.transport.requests.Request())
    except Exception as exc:
        raise CatalogUnavailableError("could not mint a Google Cloud access token") from exc
    token = getattr(credentials, "token", None)
    if not isinstance(token, str) or not token:
        raise CatalogUnavailableError("Google Cloud did not return an access token")
    return token


async def _fetch_pages(project: str, token: str, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    services: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, str | int] = {"pageSize": PAGE_SIZE}
        if page_token:
            params["pageToken"] = page_token
        response = await _get_page(client, project, token, params)
        payload = response.json()
        batch = payload.get("services")
        if isinstance(batch, list):
            services.extend(item for item in batch if isinstance(item, dict))
        page_token = str(payload.get("nextPageToken") or "")
        if not page_token:
            break
        await asyncio.sleep(PAGE_PAUSE_SECONDS)
    return services


async def _get_page(
    client: httpx.AsyncClient,
    project: str,
    token: str,
    params: dict[str, str | int],
) -> httpx.Response:
    last_status = 0
    for attempt in range(RATE_LIMIT_RETRIES):
        response = await client.get(
            SERVICE_USAGE_URL.format(project=project),
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        last_status = response.status_code
        if response.status_code != 429:
            if response.status_code >= 400:
                raise CatalogUnavailableError(
                    f"Service Usage returned {response.status_code}"
                )
            return response
        retry_after = response.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else PAGE_PAUSE_SECONDS * (attempt + 1)
        except ValueError:
            delay = PAGE_PAUSE_SECONDS * (attempt + 1)
        await asyncio.sleep(delay)
    raise CatalogUnavailableError(f"Service Usage returned {last_status}")


def catalog_to_payload(catalog: GoogleCatalog) -> dict[str, Any]:
    return {
        "provider": {
            "id": "google",
            "name": "Google Cloud",
            "slug": "google",
            "website": "https://cloud.google.com",
            "category": "cloud",
            "description": (
                "Committed Service Usage snapshot. Provider material is untrusted input."
            ),
            "verified": True,
        },
        "source": catalog.source,
        "project": catalog.project,
        "fetched_at": catalog.fetched_at,
        "services": [
            {
                "id": service.id,
                "name": service.name,
                "slug": service.slug,
                "product": service.product,
                "group": service.group,
                "summary": service.summary,
                "status": service.status,
                "identifiers": list(service.identifiers),
                "docsUrl": service.docs_url,
                "watchers": 0,
                "lastPublishedAt": catalog.fetched_at,
            }
            for service in catalog.services
        ],
    }


def catalog_from_payload(payload: Mapping[str, Any]) -> GoogleCatalog:
    rows = payload.get("services")
    if not isinstance(rows, list):
        raise CatalogUnavailableError("google catalog snapshot is malformed")
    services: list[CatalogService] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        identifiers = row.get("identifiers")
        services.append(
            CatalogService(
                id=str(row.get("id") or ""),
                name=str(row.get("name") or ""),
                slug=str(row.get("slug") or ""),
                product=str(row.get("product") or ""),
                group=str(row.get("group") or "api"),
                summary=str(row.get("summary") or ""),
                status=str(row.get("status") or "live"),
                identifiers=tuple(str(item) for item in identifiers)
                if isinstance(identifiers, list)
                else (),
                docs_url=str(row.get("docsUrl") or ""),
            )
        )
    return GoogleCatalog(
        project=str(payload.get("project") or "google"),
        fetched_at=str(payload.get("fetched_at") or ""),
        source=str(payload.get("source") or "snapshot"),
        services=tuple(service for service in services if service.id),
    )


def load_google_catalog(*, path: Path | None = None) -> GoogleCatalog:
    """Return the committed catalog snapshot.

    Live Service Usage is only used to regenerate this file. Serving reads
    the snapshot so a page load never depends on Google quota.
    """
    snapshot = path or catalog_path()
    try:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogUnavailableError("google catalog snapshot is missing") from exc
    except json.JSONDecodeError as exc:
        raise CatalogUnavailableError("google catalog snapshot is malformed") from exc
    if not isinstance(payload, dict):
        raise CatalogUnavailableError("google catalog snapshot is malformed")
    return catalog_from_payload(payload)


async def refresh_google_catalog(
    *,
    environ: Mapping[str, str] | None = None,
    base_dir: Path | None = None,
    client: httpx.AsyncClient | None = None,
    now: float | None = None,
    dest: Path | None = None,
) -> GoogleCatalog:
    """Fetch Service Usage and rewrite the committed snapshot."""
    clock = time.time() if now is None else now
    key_path = credentials_path(environ, base_dir=base_dir)
    project = project_id(key_path, environ)
    token = await asyncio.to_thread(_mint_token, key_path)
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock))

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        raw_services = await _fetch_pages(project, token, http)
    finally:
        if own_client:
            await http.aclose()

    normalized = tuple(
        service
        for service in (normalize_service(raw) for raw in raw_services)
        if service is not None
    )
    catalog = GoogleCatalog(
        project="google",
        fetched_at=fetched_at,
        source="serviceusage.googleapis.com",
        services=normalized,
    )
    target = dest or catalog_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(catalog_to_payload(catalog), indent=2) + "\n", encoding="utf-8")
    return catalog
