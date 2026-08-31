import pytest

from packages.events import (
    ENVELOPE_VERSION,
    ActionType,
    EventEnvelope,
    EventType,
    PayloadError,
    TrustLevel,
    idempotency_key,
    key_digest,
)

BASE_SHA = "c5428cdcdcd12204e1f4cc47c393dc6e738d88b2"


def make_envelope(**overrides):
    fields = {
        "event_type": EventType.PROVIDER_CHANGE_DETECTED,
        "event_id": "evt-0001",
        "run_id": "run-storygen-001",
        "occurred_at": "2026-08-11T23:00:00Z",
        "trust": TrustLevel.UNTRUSTED_PROVIDER_INPUT,
        "payload": {
            "change_id": "google-imagen4-retirement",
            "source_uri": "https://cloud.google.com/vertex-ai/docs/deprecations",
        },
    }
    return EventEnvelope(**{**fields, **overrides})


def test_envelope_round_trips_through_json():
    envelope = make_envelope()

    assert EventEnvelope.from_json(envelope.to_json()) == envelope


def test_serialization_is_stable():
    assert make_envelope().to_json() == make_envelope().to_json()


def test_provenance_is_carried():
    assert make_envelope().is_untrusted
    assert not make_envelope(trust=TrustLevel.INTERNAL_ANALYSIS).is_untrusted


def test_source_code_cannot_ride_along_in_a_payload():
    with pytest.raises(PayloadError, match="events carry references"):
        make_envelope(payload={"diff": "x" * 3000})


def test_nested_structures_are_refused():
    with pytest.raises(PayloadError, match="flat maps"):
        make_envelope(payload={"finding": {"path": "cli/src/image.ts"}})
    with pytest.raises(PayloadError, match="scalars only"):
        make_envelope(payload={"paths": [{"path": "a.ts"}]})


def test_lists_of_scalars_are_allowed():
    envelope = make_envelope(payload={"paths": ["cli/src/image.ts", "cli/src/models.ts"]})

    assert EventEnvelope.from_json(envelope.to_json()) == envelope


def test_envelope_version_is_pinned():
    with pytest.raises(ValueError, match="pinned at version"):
        make_envelope(envelope_version="0.9.0")
    assert make_envelope().envelope_version == ENVELOPE_VERSION


def test_unknown_fields_are_rejected_on_decode():
    record = make_envelope().to_dict()
    record["source_code"] = "..."

    with pytest.raises(ValueError, match="unknown fields"):
        EventEnvelope.from_dict(record)


def test_missing_fields_are_rejected_on_decode():
    record = make_envelope().to_dict()
    del record["trust"]

    with pytest.raises(ValueError, match="missing required fields"):
        EventEnvelope.from_dict(record)


def test_topic_vocabulary_matches_the_roadmap():
    assert {
        "provider-change-detected",
        "change-normalized",
        "repo-impact-requested",
        "repo-affected",
        "patch-requested",
        "sandbox-complete",
        "verification-requested",
        "pr-requested",
        "repo-push",
        "project-repo-added",
        "project-repo-removed",
        "index-updated",
    } <= {event.value for event in EventType}


def test_idempotency_key_is_the_documented_triple():
    key = idempotency_key("run-storygen-001", ActionType.OPEN_PULL_REQUEST, BASE_SHA)

    assert key == f"run-storygen-001:open_pull_request:{BASE_SHA}"
    assert key == idempotency_key("run-storygen-001", "open_pull_request", BASE_SHA)
    assert len(key_digest(key)) == 64


def test_idempotency_key_distinguishes_attempts_against_different_base_shas():
    other = "0" * 40
    assert idempotency_key("run-1", ActionType.COMMIT_PATCH, BASE_SHA) != idempotency_key(
        "run-1", ActionType.COMMIT_PATCH, other
    )


@pytest.mark.parametrize("bad_sha", ["c09e1a4", "main", "C09E1A44200FF5E951746E013035E68AEB3A14B1"])
def test_idempotency_key_requires_a_pinned_sha(bad_sha):
    with pytest.raises(ValueError):
        idempotency_key("run-1", ActionType.OPEN_PULL_REQUEST, bad_sha)


def test_unknown_action_type_fails_closed():
    with pytest.raises(ValueError):
        idempotency_key("run-1", "merge_pull_request", BASE_SHA)


def test_trust_vocabulary_matches_the_pinned_contract():
    schema_enums = pytest.importorskip(
        "packages.schemas.enums", reason="packages/schemas is not installed in this environment"
    )

    assert {level.value for level in TrustLevel} == {
        level.value for level in schema_enums.TrustClassification
    }
