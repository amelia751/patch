"""Does the registry still ship the SDK this tree depends on?

The model check asks a publisher which models it still lists. This asks the same
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
model check. A rate-limited registry answers 429, and reading that as "your SDK
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

from packages.providers import registry
from packages.providers.live_result import LiveResult, LiveStatus

NPM: Final[str] = "npm"
PYPI: Final[str] = "pypi"
GO: Final[str] = "go"

SDK_ECOSYSTEMS: Final[tuple[str, ...]] = (NPM, PYPI, GO)
SDK_SEPARATOR: Final[str] = ":"

REQUEST_TIMEOUT_SECONDS: Final[float] = 20.0

NPM_REGISTRY: Final[str] = "https://registry.npmjs.org"
PYPI_REGISTRY: Final[str] = "https://pypi.org/pypi"
GO_PROXY: Final[str] = "https://proxy.golang.org"

# Which packages are a provider's own client library, and which hosts each of
# them calls, come from that provider's descriptor. Anything outside the
# registered descriptors is somebody else's dependency and is not PatchAPI's
# business.
#
# Read through the registry on every call rather than snapshotted at import: a
# descriptor loaded from Postgres after startup must widen the watched set
# without a restart, and a stale snapshot would report a repository as having no
# SDK dependency on a provider it had just subscribed to.


def provider_packages() -> Mapping[str, tuple[tuple[str, str], ...]]:
    """Provider slug -> the `(ecosystem, name)` pairs it publishes."""
    return {
        descriptor.provider_id: descriptor.package_refs()
        for descriptor in registry.descriptors()
    }


def package_service_hosts() -> Mapping[str, tuple[str, ...]]:
    """SDK identifier -> the API hosts that client library talks to.

    A tree that depends on `google-genai` calls Vertex AI whether or not the
    hostname appears in its source, so a whole-service shutdown reaches it
    through the manifest when nothing in the code names the host.
    """
    hosts: dict[str, tuple[str, ...]] = {}
    for descriptor in registry.descriptors():
        hosts.update(descriptor.service_hosts())
    return hosts

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
    for provider, entries in provider_packages().items():
        if wanted in entries:
            return provider
    return None


def watched_packages(provider: str) -> tuple[str, ...]:
    """Every SDK identifier tracked for `provider`.

    An unregistered provider tracks nothing rather than raising: this answers
    "which of the provider's packages should be polled", and a provider with no
    descriptor has no packages, which is a true and harmless answer. The
    fail-closed reads are the ones that decide whether a repository is affected.
    """
    return tuple(
        sdk_identifier(ecosystem, name)
        for ecosystem, name in provider_packages().get(provider, ())
    )


def service_hosts_for_package(identifier: str) -> tuple[str, ...]:
    """The API hosts this client library calls, or nothing when it is unmapped."""
    return package_service_hosts().get(identifier.strip(), ())


def packages_calling(hosts: Iterable[str]) -> tuple[str, ...]:
    """Every watched package that speaks to any of `hosts`."""
    wanted = {host.strip() for host in hosts if host.strip()}
    if not wanted:
        return ()
    return tuple(
        identifier
        for identifier, served in package_service_hosts().items()
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


def package_live_result(identifier: str, release: PackageRelease | None) -> LiveResult:
    """Existence only. Deprecation is a notice, not a disappearance."""
    ecosystem = (split_sdk_identifier(identifier) or ("", ""))[0]
    if release is None:
        return LiveResult(
            identifier=identifier,
            surface=ecosystem or "registry",
            status=LiveStatus.UNKNOWN,
            checked_at=_now(),
            detail="registry did not answer; existence unknown",
            source_url="",
        )
    status = LiveStatus.RESOLVES if release.exists else LiveStatus.NOT_FOUND
    detail = (
        f"{ecosystem} publishes {release.name} at {release.latest}"
        if release.exists
        else f"{ecosystem} no longer serves {release.name}"
    )
    return LiveResult(
        identifier=identifier,
        surface=ecosystem or "registry",
        status=status,
        checked_at=release.checked_at,
        detail=detail,
        source_url=release.source_url,
    )


async def live_packages(
    identifiers: Iterable[str], *, client: httpx.AsyncClient | None = None
) -> tuple[LiveResult, ...]:
    """The SDK half of the inventory check, in the shape the poller expects."""
    wanted = [item for item in identifiers if is_sdk_identifier(item)]
    if not wanted:
        return ()
    releases = await fetch_packages(wanted, client=client)
    return tuple(package_live_result(item, releases.get(item)) for item in wanted)


__all__ = [
    "GO",
    "NPM",
    "PYPI",
    "SDK_ECOSYSTEMS",
    "PackageRelease",
    "RegistryUnavailableError",
    "fetch_package",
    "fetch_packages",
    "is_sdk_identifier",
    "live_packages",
    "major_of",
    "package_live_result",
    "package_service_hosts",
    "packages_calling",
    "provider_for_package",
    "provider_packages",
    "sdk_identifier",
    "service_hosts_for_package",
    "split_sdk_identifier",
    "watched_packages",
]
