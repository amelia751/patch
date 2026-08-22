"""Does this model identifier still resolve today?

The inbox used to decide "already broken" from `effective_at`, a date typed by
hand into a watchlist. That is a claim about the world, not an observation of
it: `imagen-4.0-generate-001` returned 404 from `v1beta` while the pinned date
still read as future, so a live call site sat in Watching.

This module replaces the claim with the check the caller's own code would make.
It lists the identifiers each surface currently publishes and reports membership.

Three outcomes, and the third is the point. `UNKNOWN` means the probe could not
run — no key, no network, a 500 from Google. It is never folded into
`NOT_FOUND`, because "I could not look" and "it is gone" justify opposite
actions, and only one of them may open a pull request (roadmap constraint 10).

Surface URLs and credential resolution are duplicated from
`packages.state.google_models` rather than imported: `patchapi-state` depends on
this package, so importing back the other way would close a cycle.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import httpx

from packages.providers.google.errors import GoogleProviderError

GEMINI_MODELS_URL: Final[str] = "https://generativelanguage.googleapis.com/v1beta/models"
VERTEX_MODELS_URLS: Final[tuple[str, ...]] = (
    "https://aiplatform.googleapis.com/v1beta1/publishers/google/models",
    "https://us-central1-aiplatform.googleapis.com/v1beta1/publishers/google/models",
)
CLOUD_PLATFORM_SCOPE: Final[str] = "https://www.googleapis.com/auth/cloud-platform"
DEFAULT_GEMINI_KEY_FILE: Final[str] = ".secrets/gemini_api_key.txt"
DEFAULT_CREDENTIALS_FILE: Final[str] = ".secrets/gcp-service-account.json"

REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0
PAGE_SIZE: Final[int] = 100

GEMINI_API: Final[str] = "gemini_api"
VERTEX: Final[str] = "vertex"

# `vertex/imagen-4.0-generate-001` is a routing decision plus a model id. The
# prefix says which surface to probe; it is not part of the identifier.
VERTEX_PREFIX: Final[str] = "vertex/"
MODELS_PREFIX: Final[str] = "models/"

# Identifiers that are not Google first-party model ids. Probing them would ask
# Google whether someone else's model exists, and a "no" would be meaningless.
FOREIGN_PREFIXES: Final[tuple[str, ...]] = ("fal-ai/", "openai/", "anthropic/", "replicate/")


class ProbeUnavailableError(GoogleProviderError):
    """The probe could not reach a surface. Not evidence of retirement."""


class ProbeStatus(StrEnum):
    """What the live surface said about an identifier."""

    RESOLVES = "resolves"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """One identifier, checked against one surface, at one moment."""

    identifier: str
    surface: str
    status: ProbeStatus
    checked_at: str
    detail: str
    source_url: str

    def to_evidence(self) -> dict[str, Any]:
        """JSON-safe record for a trace, a manifest, or a PR body."""
        return {
            "identifier": self.identifier,
            "surface": self.surface,
            "status": str(self.status),
            "checked_at": self.checked_at,
            "detail": self.detail,
            "source_url": self.source_url,
        }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def canonical_probe_id(identifier: str) -> tuple[str, str]:
    """Split an inventory identifier into the surface to ask and the id to ask for."""
    raw = identifier.strip()
    if raw.startswith(VERTEX_PREFIX):
        return VERTEX, raw.removeprefix(VERTEX_PREFIX).removeprefix(MODELS_PREFIX)
    return GEMINI_API, raw.removeprefix(MODELS_PREFIX)


def is_probeable(identifier: str) -> bool:
    """False for third-party ids and for anything that is not a model name."""
    raw = identifier.strip().lower()
    if not raw:
        return False
    return not raw.startswith(FOREIGN_PREFIXES)


def strip_model_name(name: str) -> str:
    """`publishers/google/models/imagen-4.0-generate-001` -> the bare id."""
    value = name.strip()
    if "/models/" in value:
        return value.rsplit("/models/", 1)[-1]
    return value.removeprefix(MODELS_PREFIX)


def gemini_key(environ: Mapping[str, str] | None, base_dir: Path | None) -> str:
    env = os.environ if environ is None else environ
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        value = env.get(name, "").strip()
        if value:
            return value
    root = _repo_root() if base_dir is None else base_dir
    path = root / DEFAULT_GEMINI_KEY_FILE
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    raise ProbeUnavailableError("Gemini API key is not configured")


def credentials_file(environ: Mapping[str, str] | None, base_dir: Path | None) -> Path:
    env = os.environ if environ is None else environ
    root = _repo_root() if base_dir is None else base_dir
    raw = env.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip() or DEFAULT_CREDENTIALS_FILE
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else (root / candidate)


def mint_token(key_path: Path) -> str:
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise ProbeUnavailableError("google-auth is not installed") from exc
    if not key_path.is_file():
        raise ProbeUnavailableError("Google Cloud credentials are not configured")
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(key_path), scopes=[CLOUD_PLATFORM_SCOPE]
        )
        credentials.refresh(google.auth.transport.requests.Request())
    except Exception as exc:  # google-auth raises a wide, undocumented family
        raise ProbeUnavailableError(f"could not mint a Google access token: {exc}") from exc
    token = str(credentials.token or "")
    if not token:
        raise ProbeUnavailableError("Google returned an empty access token")
    return token


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _source_url(surface: str) -> str:
    return GEMINI_MODELS_URL if surface == GEMINI_API else VERTEX_MODELS_URLS[0]


async def published_gemini(client: httpx.AsyncClient, key: str) -> set[str]:
    """Every model id `generativelanguage` currently lists."""
    published: set[str] = set()
    page_token = ""
    while True:
        params: dict[str, str | int] = {"key": key, "pageSize": PAGE_SIZE}
        if page_token:
            params["pageToken"] = page_token
        response = await client.get(GEMINI_MODELS_URL, params=params)
        if response.status_code >= 400:
            raise ProbeUnavailableError(f"Gemini models.list returned {response.status_code}")
        payload = response.json()
        for item in payload.get("models") or ():
            if isinstance(item, dict):
                published.add(strip_model_name(str(item.get("name") or "")))
        page_token = str(payload.get("nextPageToken") or "")
        if not page_token:
            break
    return {name for name in published if name}


async def published_vertex(client: httpx.AsyncClient, token: str) -> set[str]:
    """Every publisher model id Vertex currently lists."""
    published: set[str] = set()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    for url in VERTEX_MODELS_URLS:
        page_token = ""
        while True:
            params: dict[str, str | int] = {"pageSize": PAGE_SIZE}
            if page_token:
                params["pageToken"] = page_token
            response = await client.get(url, headers=headers, params=params)
            if response.status_code >= 400:
                raise ProbeUnavailableError(
                    f"Vertex publishers.models.list returned {response.status_code}"
                )
            payload = response.json()
            for item in payload.get("publisherModels") or payload.get("models") or ():
                if isinstance(item, dict):
                    published.add(strip_model_name(str(item.get("name") or "")))
            page_token = str(payload.get("nextPageToken") or "")
            if not page_token:
                break
    return {name for name in published if name}


def decide(
    *,
    identifier: str,
    surface: str,
    probe_id: str,
    published: set[str] | None,
    detail: str,
) -> ProbeResult:
    """Membership against a listing, or UNKNOWN when there is no listing."""
    if published is None:
        status, note = ProbeStatus.UNKNOWN, detail
    elif probe_id in published:
        status, note = ProbeStatus.RESOLVES, f"{surface} lists {probe_id}"
    else:
        status, note = ProbeStatus.NOT_FOUND, f"{surface} does not list {probe_id}"
    return ProbeResult(
        identifier=identifier,
        surface=surface,
        status=status,
        checked_at=_now(),
        detail=note,
        source_url=_source_url(surface),
    )


async def _listing(
    surface: str,
    client: httpx.AsyncClient,
    environ: Mapping[str, str] | None,
    base_dir: Path | None,
) -> set[str]:
    if surface == GEMINI_API:
        return await published_gemini(client, gemini_key(environ, base_dir))
    token = await asyncio.to_thread(mint_token, credentials_file(environ, base_dir))
    return await published_vertex(client, token)


async def probe_identifiers(
    identifiers: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
    base_dir: Path | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[ProbeResult, ...]:
    """Ask each surface which of `identifiers` it still publishes.

    One listing call per surface, not one per identifier: the answer to "does
    this resolve" is membership in a list Google already hands out whole.
    """
    targets: list[tuple[str, str, str]] = []
    skipped: list[ProbeResult] = []
    for identifier in identifiers:
        if not is_probeable(identifier):
            skipped.append(
                ProbeResult(
                    identifier=identifier,
                    surface="none",
                    status=ProbeStatus.UNKNOWN,
                    checked_at=_now(),
                    detail="not a Google first-party model id; nothing to probe",
                    source_url="",
                )
            )
            continue
        surface, probe_id = canonical_probe_id(identifier)
        targets.append((identifier, surface, probe_id))

    if not targets:
        return tuple(skipped)

    owned = client is None
    http = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    listings: dict[str, set[str] | None] = {}
    details: dict[str, str] = {}
    try:
        for surface in sorted({surface for _, surface, _ in targets}):
            try:
                listings[surface] = await _listing(surface, http, environ, base_dir)
                details[surface] = ""
            except (ProbeUnavailableError, httpx.HTTPError, OSError, ValueError) as exc:
                listings[surface] = None
                details[surface] = f"probe unavailable: {exc}"
    finally:
        if owned:
            await http.aclose()

    results = [
        decide(
            identifier=identifier,
            surface=surface,
            probe_id=probe_id,
            published=listings.get(surface),
            detail=details.get(surface, "probe unavailable"),
        )
        for identifier, surface, probe_id in targets
    ]
    return tuple(skipped + results)


def retired_identifiers(results: Iterable[ProbeResult]) -> tuple[str, ...]:
    """Identifiers a surface has stopped publishing. UNKNOWN is not retired."""
    return tuple(result.identifier for result in results if result.status is ProbeStatus.NOT_FOUND)


__all__ = [
    "GEMINI_API",
    "VERTEX",
    "ProbeResult",
    "ProbeStatus",
    "ProbeUnavailableError",
    "canonical_probe_id",
    "decide",
    "is_probeable",
    "mint_token",
    "probe_identifiers",
    "retired_identifiers",
]
