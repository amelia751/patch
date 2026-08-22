"""Retirements found on the wire, with no notice to cite."""

import pytest

from packages.providers.google.probe import GEMINI_API, VERTEX, ProbeResult, ProbeStatus
from packages.state.discovery import discovery_event, undocumented_retirements


def _probe(
    identifier: str,
    status: ProbeStatus = ProbeStatus.NOT_FOUND,
    surface: str = GEMINI_API,
) -> ProbeResult:
    return ProbeResult(
        identifier=identifier,
        surface=surface,
        status=status,
        checked_at="2026-08-22T12:00:00+00:00",
        detail=f"{surface} does not list {identifier}",
        source_url="https://generativelanguage.googleapis.com/v1beta/models",
    )


class _Connection:
    """Stands in for asyncpg: `covered_identifiers` is the only read reached."""

    def __init__(self, covered: list[str]) -> None:
        self._covered = covered

    async def fetch(self, _sql: str, *_args: object) -> list[dict[str, object]]:
        return [{"affected_identifiers": self._covered}]


def test_a_discovered_retirement_names_no_replacement() -> None:
    """The probe proves the model is gone and nothing about what replaces it."""
    note = discovery_event(_probe("imagen-4.0-generate-001"))
    assert note["replacements"] == []
    assert note["fail_closed"] is True
    assert note["migration"] is None
    assert note["identifiers"] == ["imagen-4.0-generate-001"]
    assert note["change_kind"] == "breaking_change"


def test_a_discovered_retirement_is_dated_when_observed() -> None:
    note = discovery_event(_probe("imagen-4.0-generate-001"))
    assert note["effective_at"] == "2026-08-22"
    assert note["announced_at"] is None
    assert "no published notice" in note["summary"]


def test_the_surface_is_named_in_the_summary() -> None:
    vertex = discovery_event(_probe("vertex/imagen-4.0-generate-001", surface=VERTEX))
    assert "Vertex AI" in vertex["summary"]
    assert "the Gemini API" in discovery_event(_probe("gemini-2.0-flash"))["summary"]


@pytest.mark.asyncio
async def test_only_uncovered_dead_identifiers_are_discovered() -> None:
    results = (
        _probe("imagen-4.0-generate-001"),
        _probe("gemini-9.9-secret-model"),
        _probe("gemini-3.5-flash", status=ProbeStatus.RESOLVES),
        _probe("fal-ai/imagen4/preview", status=ProbeStatus.UNKNOWN),
    )
    connection = _Connection(["imagen-4.0-generate-001"])
    found = await undocumented_retirements(connection, results=results)
    assert [item.identifier for item in found] == ["gemini-9.9-secret-model"]


@pytest.mark.asyncio
async def test_an_unknown_probe_is_never_discovered_as_a_retirement() -> None:
    """ "Could not check" must not create a release claiming a break."""
    results = (_probe("imagen-4.0-generate-001", status=ProbeStatus.UNKNOWN),)
    found = await undocumented_retirements(_Connection([]), results=results)
    assert found == []
