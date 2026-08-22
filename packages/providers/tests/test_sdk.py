"""The package registry probe. No network: responses are injected."""

import httpx
import pytest

from packages.providers.probe_result import ProbeStatus
from packages.providers.sdk import (
    NPM,
    PYPI,
    fetch_package,
    is_sdk_identifier,
    major_of,
    npm_url,
    probe_packages,
    provider_for_package,
    sdk_identifier,
    split_sdk_identifier,
    watched_packages,
)


def test_the_ecosystem_prefix_is_part_of_the_identity() -> None:
    """`vertexai` is a real PyPI package and a real word in a Go module path;
    asking npm about the PyPI name would 404 for something that exists."""
    assert sdk_identifier("npm", "@google/genai") == "npm:@google/genai"
    assert split_sdk_identifier("pypi:google-genai") == (PYPI, "google-genai")
    assert split_sdk_identifier("gemini-3.5-flash") is None
    assert not is_sdk_identifier("imagen-4.0-generate-001")


def test_only_a_watched_provider_package_is_tracked() -> None:
    assert provider_for_package(NPM, "@google/genai") == "google"
    assert provider_for_package(NPM, "react") is None
    assert "npm:@google/genai" in watched_packages("google")


def test_major_is_read_from_a_constraint_not_only_a_version() -> None:
    assert major_of("^1.4.0") == 1
    assert major_of(">=1.2,<2") == 1
    assert major_of("v2.0.0-rc1") == 2
    assert major_of("*") is None


def test_a_scoped_name_stays_one_path_segment() -> None:
    assert npm_url("@google/genai").endswith("/@google%2Fgenai")


@pytest.mark.asyncio
async def test_an_unpublished_package_is_not_found() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        release = await fetch_package(client, NPM, "@google/gone")

    assert release.exists is False


@pytest.mark.asyncio
async def test_a_deprecation_message_is_carried_not_read_as_absence() -> None:
    payload = {
        "dist-tags": {"latest": "0.24.1"},
        "versions": {"0.24.1": {"deprecated": "Use @google/genai instead."}},
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        release = await fetch_package(client, NPM, "@google/generative-ai")

    assert release.exists is True
    assert release.latest_major == 0
    assert "Use @google/genai" in release.deprecated


@pytest.mark.asyncio
async def test_a_rate_limited_registry_is_unknown_never_retired() -> None:
    """429 read as "your SDK was unpublished" would open a pull request against
    every project at once."""
    transport = httpx.MockTransport(lambda request: httpx.Response(429))
    async with httpx.AsyncClient(transport=transport) as client:
        results = await probe_packages(["npm:@google/genai"], client=client)

    assert [result.status for result in results] == [ProbeStatus.UNKNOWN]


@pytest.mark.asyncio
async def test_a_published_package_resolves() -> None:
    payload = {"dist-tags": {"latest": "2.1.0"}, "versions": {"2.1.0": {}}}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        results = await probe_packages(["npm:@google/genai"], client=client)

    assert results[0].status is ProbeStatus.RESOLVES
    assert results[0].surface == NPM


@pytest.mark.asyncio
async def test_a_yanked_pypi_release_reports_its_reason() -> None:
    payload = {"info": {"version": "1.2.0", "yanked": True, "yanked_reason": "broken wheel"}}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        release = await fetch_package(client, PYPI, "google-genai")

    assert release.deprecated == "broken wheel"
