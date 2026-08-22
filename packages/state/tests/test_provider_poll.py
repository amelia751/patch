"""What the poller announces, and — more importantly — what it stays quiet about.

A false transition is worse than a missed one here: every event fans out to the
deterministic subscriber and to a Change Intelligence run, so a poller that
re-announces yesterday's retirement every fifteen minutes burns money and fills
the tab with duplicates.
"""

import pytest

from packages.events.config import EventType
from packages.events.provider_events import (
    TRANSITION_APPEARED,
    TRANSITION_RESTORED,
    TRANSITION_RETIRED,
)
from packages.events.publisher import PublishResult
from packages.providers.google.probe import ProbeResult, ProbeStatus
from packages.state import provider_poll
from packages.state.provider_poll import (
    NO_PREVIOUS,
    announce,
    classify_transition,
    detect_transitions,
)

GEMINI = "gemini_api"


def probe(identifier: str, status: ProbeStatus, surface: str = GEMINI) -> ProbeResult:
    return ProbeResult(
        identifier=identifier,
        surface=surface,
        status=status,
        checked_at="2026-08-22T18:00:00+00:00",
        detail="",
        source_url="https://example.invalid/models",
    )


def test_a_model_that_stops_resolving_is_a_retirement() -> None:
    assert classify_transition("resolves", ProbeStatus.NOT_FOUND) == TRANSITION_RETIRED


def test_a_model_still_missing_is_not_news() -> None:
    assert classify_transition("not_found", ProbeStatus.NOT_FOUND) is None


def test_a_model_still_serving_is_not_news() -> None:
    assert classify_transition("resolves", ProbeStatus.RESOLVES) is None


def test_first_sight_of_a_dead_model_is_announced() -> None:
    # Never probed before and already gone: the retirement is real and nobody
    # has heard about it yet.
    assert classify_transition(NO_PREVIOUS, ProbeStatus.NOT_FOUND) == TRANSITION_RETIRED


def test_first_sight_of_a_live_model_is_only_an_appearance() -> None:
    assert classify_transition(NO_PREVIOUS, ProbeStatus.RESOLVES) == TRANSITION_APPEARED


def test_a_model_that_comes_back_is_a_restoration() -> None:
    assert classify_transition("not_found", ProbeStatus.RESOLVES) == TRANSITION_RESTORED


def test_a_failed_check_never_announces_anything() -> None:
    for previous in (NO_PREVIOUS, "resolves", "not_found", "unknown"):
        assert classify_transition(previous, ProbeStatus.UNKNOWN) is None


def test_leaving_unknown_for_a_404_is_a_retirement() -> None:
    # The only way to hold `unknown` is for the very first check to have failed,
    # so arriving at a definite 404 is the first real answer about this id.
    assert classify_transition("unknown", ProbeStatus.NOT_FOUND) == TRANSITION_RETIRED


def test_a_steady_state_poll_announces_nothing() -> None:
    previous = {
        ("imagen-4.0-generate-001", GEMINI): "not_found",
        ("gemini-3.5-flash", GEMINI): "resolves",
    }
    results = (
        probe("imagen-4.0-generate-001", ProbeStatus.NOT_FOUND),
        probe("gemini-3.5-flash", ProbeStatus.RESOLVES),
    )
    assert detect_transitions(previous, results) == []


def test_only_the_changed_identifier_is_announced() -> None:
    previous = {
        ("imagen-4.0-generate-001", GEMINI): "not_found",
        ("gemini-3.5-flash", GEMINI): "resolves",
    }
    results = (
        probe("imagen-4.0-generate-001", ProbeStatus.NOT_FOUND),
        probe("gemini-3.5-flash", ProbeStatus.NOT_FOUND),
    )
    transitions = detect_transitions(previous, results)
    assert [change.identifier for change in transitions] == ["gemini-3.5-flash"]
    assert transitions[0].transition == TRANSITION_RETIRED
    assert transitions[0].previous_status == "resolves"


def test_the_same_id_on_two_surfaces_is_tracked_separately() -> None:
    previous = {("imagen-4.0-generate-001", GEMINI): "not_found"}
    results = (
        probe("imagen-4.0-generate-001", ProbeStatus.NOT_FOUND),
        probe("imagen-4.0-generate-001", ProbeStatus.NOT_FOUND, surface="vertex"),
    )
    transitions = detect_transitions(previous, results)
    # Gemini already knew; Vertex is a first observation of a dead model.
    assert [change.surface for change in transitions] == ["vertex"]


def _result(published: bool) -> PublishResult:
    return PublishResult(
        event_type=EventType.PROVIDER_CHANGE_DETECTED,
        event_id="e",
        topic="t",
        published=published,
        reason=None if published else "PermissionDenied",
    )


@pytest.mark.asyncio
async def test_an_unpublished_transition_is_reported_so_its_row_is_held_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug this guards: committing the probe row before the message lands.

    The stored status is the only memory of what the last poll concluded. Write
    `not_found`, fail to publish, and the next poll sees no change — the
    retirement is announced by nobody, ever.
    """

    async def denied(_envelope: object) -> PublishResult:
        return _result(published=False)

    monkeypatch.setattr(provider_poll, "publish_async", denied)
    transitions = detect_transitions(
        {("imagen-4.0-generate-001", GEMINI): "resolves"},
        (probe("imagen-4.0-generate-001", ProbeStatus.NOT_FOUND),),
    )
    published, failed = await announce(transitions, provider="google")
    assert published == []
    assert failed == {("imagen-4.0-generate-001", GEMINI)}


@pytest.mark.asyncio
async def test_a_published_transition_leaves_nothing_held_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def accepted(_envelope: object) -> PublishResult:
        return _result(published=True)

    monkeypatch.setattr(provider_poll, "publish_async", accepted)
    transitions = detect_transitions(
        {("imagen-4.0-generate-001", GEMINI): "resolves"},
        (probe("imagen-4.0-generate-001", ProbeStatus.NOT_FOUND),),
    )
    published, failed = await announce(transitions, provider="google")
    assert len(published) == 1
    assert failed == set()
