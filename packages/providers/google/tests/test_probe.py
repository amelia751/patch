"""The live identifier probe. No network: listings are injected."""

import httpx
import pytest

from packages.providers.google.probe import (
    GEMINI_API,
    VERTEX,
    ProbeStatus,
    canonical_probe_id,
    decide,
    is_probeable,
    is_service_identifier,
    probe_identifiers,
    retired_identifiers,
    strip_model_name,
)


def test_vertex_prefix_selects_the_surface_not_the_id() -> None:
    assert canonical_probe_id("vertex/imagen-4.0-generate-001") == (
        VERTEX,
        "imagen-4.0-generate-001",
    )
    assert canonical_probe_id("models/gemini-3.5-flash") == (GEMINI_API, "gemini-3.5-flash")
    assert canonical_probe_id("gemini-3.5-flash") == (GEMINI_API, "gemini-3.5-flash")


def test_third_party_ids_are_not_probeable() -> None:
    assert not is_probeable("fal-ai/imagen4/preview")
    assert not is_probeable("")
    assert is_probeable("imagen-4.0-generate-001")


def test_a_service_host_is_never_probed_as_a_model() -> None:
    """The model listing has no row for a hostname, so probing one would report
    a running service as retired and the poller would announce it."""
    assert is_service_identifier("aiplatform.googleapis.com")
    assert not is_probeable("aiplatform.googleapis.com")
    assert not is_probeable("generativelanguage.googleapis.com")


def test_strip_model_name_handles_both_resource_shapes() -> None:
    assert strip_model_name("publishers/google/models/imagen-4.0-generate-001") == (
        "imagen-4.0-generate-001"
    )
    assert strip_model_name("models/gemini-3.5-flash") == "gemini-3.5-flash"


def test_missing_from_the_listing_is_not_found() -> None:
    result = decide(
        identifier="imagen-4.0-generate-001",
        surface=GEMINI_API,
        probe_id="imagen-4.0-generate-001",
        published={"gemini-3.5-flash"},
        detail="",
    )
    assert result.status is ProbeStatus.NOT_FOUND


def test_no_listing_is_unknown_never_not_found() -> None:
    """ "I could not look" and "it is gone" justify opposite actions."""
    result = decide(
        identifier="imagen-4.0-generate-001",
        surface=GEMINI_API,
        probe_id="imagen-4.0-generate-001",
        published=None,
        detail="probe unavailable: no key",
    )
    assert result.status is ProbeStatus.UNKNOWN
    assert retired_identifiers([result]) == ()


def test_retired_identifiers_reports_only_not_found() -> None:
    published = {"gemini-3.5-flash"}
    results = [
        decide(
            identifier=name,
            surface=GEMINI_API,
            probe_id=name,
            published=published,
            detail="",
        )
        for name in ("gemini-3.5-flash", "imagen-4.0-generate-001")
    ]
    assert retired_identifiers(results) == ("imagen-4.0-generate-001",)


@pytest.mark.asyncio
async def test_a_failing_surface_yields_unknown_not_retirement() -> None:
    """A 500 from Google must not read as "every model was retired"."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await probe_identifiers(
            ["imagen-4.0-generate-001"],
            environ={"GOOGLE_API_KEY": "test-key"},
            client=client,
        )
    assert [r.status for r in results] == [ProbeStatus.UNKNOWN]
    assert retired_identifiers(results) == ()


@pytest.mark.asyncio
async def test_a_live_listing_separates_present_from_gone() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"models": [{"name": "models/gemini-3.5-flash"}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        results = await probe_identifiers(
            ["gemini-3.5-flash", "imagen-4.0-generate-001", "fal-ai/imagen4/preview"],
            environ={"GOOGLE_API_KEY": "test-key"},
            client=client,
        )
    by_id = {r.identifier: r.status for r in results}
    assert by_id["gemini-3.5-flash"] is ProbeStatus.RESOLVES
    assert by_id["imagen-4.0-generate-001"] is ProbeStatus.NOT_FOUND
    assert by_id["fal-ai/imagen4/preview"] is ProbeStatus.UNKNOWN
