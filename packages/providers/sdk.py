"""Does the registry still ship the SDK this tree depends on?

The model probe asks a publisher which models it still lists. This asks the same
question of a package registry, because the other way a provider breaks a
customer is through the client library: the package is unpublished, the author
marks it deprecated in favour of a rewrite, or a new major lands with a
different surface.

An SDK identifier carries its registry: `npm:@google/genai`, `pypi:google-genai`.
The prefix is not decoration — `vertexai` is a real package on PyPI and a real
word in a Go module path, and asking npm about a PyPI name would answer 404 for
something that exists.

Only packages belonging to a watched provider are tracked. PatchAPI is not a
dependency updater; a break only matters here when it comes from an API provider
the project subscribed to.

`UNKNOWN` stays separate from `NOT_FOUND` for the same reason it does in the
model probe. A rate-limited registry answers 429, and reading that as "your SDK
was unpublished" would open pull requests against every project at once.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import quote

import httpx

from packages.providers.probe_result import ProbeResult, ProbeStatus

NPM: Final[str] = "npm"
PYPI: Final[str] = "pypi"
GO: Final[str] = "go"

SDK_ECOSYSTEMS: Final[tuple[str, ...]] = (NPM, PYPI, GO)
SDK_SEPARATOR: Final[str] = ":"

REQUEST_TIMEOUT_SECONDS: Final[float] = 20.0

NPM_REGISTRY: Final[str] = "https://registry.npmjs.org"
PYPI_REGISTRY: Final[str] = "https://pypi.org/pypi"
GO_PROXY: Final[str] = "https://proxy.golang.org"

# Packages that are the provider's own client library. Anything outside this map
# is somebody else's dependency and is not PatchAPI's business.
PROVIDER_PACKAGES: Final[Mapping[str, tuple[tuple[str, str], ...]]] = {
    "google": (
        (NPM, "@google/genai"),
        (NPM, "@google/generative-ai"),
        (NPM, "@google-cloud/aiplatform"),
        (NPM, "@google-cloud/vertexai"),
        (PYPI, "google-genai"),
        (PYPI, "google-generativeai"),
        (PYPI, "google-cloud-aiplatform"),
        (PYPI, "vertexai"),
        (GO, "google.golang.org/genai"),
        (GO, "cloud.google.com/go/aiplatform"),
    ),
}

# The API host each client library talks to. A tree that depends on
# `google-genai` calls Vertex AI whether or not the hostname appears in its
# source, so a whole-service shutdown reaches it through the manifest when
# nothing in the code names the host.
PACKAGE_SERVICE_HOSTS: Final[Mapping[str, tuple[str, ...]]] = {
    "npm:@google/genai": ("generativelanguage.googleapis.com", "aiplatform.googleapis.com"),
    "npm:@google/generative-ai": ("generativelanguage.googleapis.com",),
    "npm:@google-cloud/aiplatform": ("aiplatform.googleapis.com",),
    "npm:@google-cloud/vertexai": ("aiplatform.googleapis.com",),
    "pypi:google-genai": ("generativelanguage.googleapis.com", "aiplatform.googleapis.com"),
    "pypi:google-generativeai": ("generativelanguage.googleapis.com",),
    "pypi:google-cloud-aiplatform": ("aiplatform.googleapis.com",),
    "pypi:vertexai": ("aiplatform.googleapis.com",),
    "go:google.golang.org/genai": (
        "generativelanguage.googleapis.com",
        "aiplatform.googleapis.com",
    ),
    "go:cloud.google.com/go/aiplatform": ("aiplatform.googleapis.com",),
}

_MAJOR: Final[re.Pattern[str]] = re.compile(r"(\d+)")


class RegistryUnavailableError(RuntimeError):
    """The registry could not be reached. Not evidence the package is gone."""


@dataclass(frozen=True, slots=True)
class PackageRelease:
    """What a registry currently says about one package."""

    ecosystem: str
    name: str
    exists: bool
    latest: str
    deprecated: str
    checked_at: str
    source_url: str

    @property
    def latest_major(self) -> int | None:
        return major_of(self.latest)


def sdk_identifier(ecosystem: str, name: str) -> str:
    """`npm` + `@google/genai` -> `npm:@google/genai`."""
    return f"{ecosystem.strip().lower()}{SDK_SEPARATOR}{name.strip()}"


def split_sdk_identifier(identifier: str) -> tuple[str, str] | None:
    """The ecosystem and package name, or None when this is not an SDK id."""
    raw = identifier.strip()
    prefix, separator, name = raw.partition(SDK_SEPARATOR)
    if not separator or not name.strip():
        return None
    ecosystem = prefix.strip().lower()
    if ecosystem not in SDK_ECOSYSTEMS:
        return None
    return ecosystem, name.strip()


def is_sdk_identifier(identifier: str) -> bool:
    """True for an inventory key that names a package rather than a model."""
    return split_sdk_identifier(identifier) is not None


def provider_for_package(ecosystem: str, name: str) -> str | None:
    """The provider whose client library this is, or None when nobody's."""
    wanted = (ecosystem.strip().lower(), name.strip())
    for provider, entries in PROVIDER_PACKAGES.items():
        if wanted in entries:
            return provider
    return None


def watched_packages(provider: str) -> tuple[str, ...]:
    """Every SDK identifier tracked for `provider`."""
    return tuple(
        sdk_identifier(ecosystem, name)
        for ecosystem, name in PROVIDER_PACKAGES.get(provider, ())
    )


def service_hosts_for_package(identifier: str) -> tuple[str, ...]:
    """The API hosts this client library calls, or nothing when it is unmapped."""
    return PACKAGE_SERVICE_HOSTS.get(identifier.strip(), ())


def packages_calling(hosts: Iterable[str]) -> tuple[str, ...]:
    """Every watched package that speaks to any of `hosts`."""
    wanted = {host.strip() for host in hosts if host.strip()}
    if not wanted:
        return ()
    return tuple(
        identifier
        for identifier, served in PACKAGE_SERVICE_HOSTS.items()
        if wanted.intersection(served)
    )


def major_of(version: str) -> int | None:
    """The major from a version or a constraint. None when it does not pin one.

    `^1.4.0`, `>=1.2,<2`, `v1.4.0` and `1.4.0` all pin major 1. `*` and `latest`
    pin nothing, and a caller must not read that as major 0.
    """
    match = _MAJOR.search(version or "")
    return int(match.group(1)) if match else None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def npm_url(name: str) -> str:
    # A scoped name is one path segment, so the slash inside it must be escaped
    # or the registry reads `@google` as the package and `genai` as a revision.
    return f"{NPM_REGISTRY}/{quote(name, safe='@')}"


def pypi_url(name: str) -> str:
    return f"{PYPI_REGISTRY}/{quote(name, safe='')}/json"


def go_url(name: str) -> str:
    return f"{GO_PROXY}/{quote(name, safe='/')}/@latest"


def _npm_release(name: str, payload: Any, url: str) -> PackageRelease:
    tags = payload.get("dist-tags") if isinstance(payload, dict) else None
    latest = str((tags or {}).get("latest") or "")
    versions = payload.get("versions") if isinstance(payload, dict) else None
    entry = (versions or {}).get(latest) if isinstance(versions, dict) else None
    deprecated = str((entry or {}).get("deprecated") or "") if isinstance(entry, dict) else ""
    return PackageRelease(NPM, name, True, latest, deprecated, _now(), url)


def _pypi_release(name: str, payload: Any, url: str) -> PackageRelease:
    info = payload.get("info") if isinstance(payload, dict) else None
    info = info if isinstance(info, dict) else {}
    latest = str(info.get("version") or "")
    # PyPI has no deprecation flag. A yanked latest release is the closest
    # equivalent the API actually reports, and it says why.
    deprecated = str(info.get("yanked_reason") or "") if info.get("yanked") else ""
    return PackageRelease(PYPI, name, True, latest, deprecated, _now(), url)


def _go_release(name: str, payload: Any, url: str) -> PackageRelease:
    version = str(payload.get("Version") or "") if isinstance(payload, dict) else ""
    return PackageRelease(GO, name, True, version, "", _now(), url)


_READERS: Final[Mapping[str, Any]] = {NPM: _npm_release, PYPI: _pypi_release, GO: _go_release}
_URLS: Final[Mapping[str, Any]] = {NPM: npm_url, PYPI: pypi_url, GO: go_url}


async def fetch_package(
    client: httpx.AsyncClient, ecosystem: str, name: str
) -> PackageRelease:
    """Ask one registry about one package.

    Raises `RegistryUnavailableError` when the answer is not trustworthy, which
    the caller turns into UNKNOWN. Only a 404 is allowed to mean "gone".
    """
    url = _URLS[ecosystem](name)
    try:
        response = await client.get(url, headers={"Accept": "application/json"})
    except (httpx.HTTPError, OSError) as exc:
        raise RegistryUnavailableError(f"{ecosystem} registry unreachable: {exc}") from exc
    if response.status_code == 404:
        return PackageRelease(ecosystem, name, False, "", "", _now(), url)
    if response.status_code >= 400:
        raise RegistryUnavailableError(f"{ecosystem} registry returned {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RegistryUnavailableError(f"{ecosystem} registry returned non-JSON") from exc
    return _READERS[ecosystem](name, payload, url)


async def fetch_packages(
    identifiers: Sequence[str], *, client: httpx.AsyncClient | None = None
) -> dict[str, PackageRelease | None]:
    """Look up every SDK identifier. None means the registry could not answer."""
    wanted: list[tuple[str, str, str]] = []
    for identifier in identifiers:
        split = split_sdk_identifier(identifier)
        if split is not None:
            wanted.append((identifier, *split))
    if not wanted:
        return {}

    owned = client is None
    http = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        answers = await asyncio.gather(
            *(fetch_package(http, ecosystem, name) for _, ecosystem, name in wanted),
            return_exceptions=True,
        )
    finally:
        if owned:
            await http.aclose()

    found: dict[str, PackageRelease | None] = {}
    for (identifier, _, _), answer in zip(wanted, answers, strict=True):
        found[identifier] = answer if isinstance(answer, PackageRelease) else None
    return found


def package_probe_result(identifier: str, release: PackageRelease | None) -> ProbeResult:
    """Existence only. Deprecation is a notice, not a disappearance."""
    ecosystem = (split_sdk_identifier(identifier) or ("", ""))[0]
    if release is None:
        return ProbeResult(
            identifier=identifier,
            surface=ecosystem or "registry",
            status=ProbeStatus.UNKNOWN,
            checked_at=_now(),
            detail="registry did not answer; existence unknown",
            source_url="",
        )
    status = ProbeStatus.RESOLVES if release.exists else ProbeStatus.NOT_FOUND
    detail = (
        f"{ecosystem} publishes {release.name} at {release.latest}"
        if release.exists
        else f"{ecosystem} no longer serves {release.name}"
    )
    return ProbeResult(
        identifier=identifier,
        surface=ecosystem or "registry",
        status=status,
        checked_at=release.checked_at,
        detail=detail,
        source_url=release.source_url,
    )


async def probe_packages(
    identifiers: Iterable[str], *, client: httpx.AsyncClient | None = None
) -> tuple[ProbeResult, ...]:
    """The SDK half of the inventory probe, in the shape the poller expects."""
    wanted = [item for item in identifiers if is_sdk_identifier(item)]
    if not wanted:
        return ()
    releases = await fetch_packages(wanted, client=client)
    return tuple(package_probe_result(item, releases.get(item)) for item in wanted)


__all__ = [
    "GO",
    "NPM",
    "PACKAGE_SERVICE_HOSTS",
    "PROVIDER_PACKAGES",
    "PYPI",
    "SDK_ECOSYSTEMS",
    "PackageRelease",
    "RegistryUnavailableError",
    "fetch_package",
    "fetch_packages",
    "is_sdk_identifier",
    "major_of",
    "package_probe_result",
    "packages_calling",
    "probe_packages",
    "provider_for_package",
    "sdk_identifier",
    "service_hosts_for_package",
    "split_sdk_identifier",
    "watched_packages",
]
