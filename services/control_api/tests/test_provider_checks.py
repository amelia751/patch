from fastapi.testclient import TestClient
from patchapi_control_api.idempotency import provider_check_key

TRIGGER = {
    "provider_id": "google",
    "requested_by": "release-engineer",
    "since": "2026-08-01T00:00:00Z",
}


def test_trigger_is_accepted_and_carries_a_derived_key(client: TestClient, dispatcher) -> None:
    response = client.post("/v1/provider-checks", json=TRIGGER)

    assert response.status_code == 202
    body = response.json()
    assert body["created"] is True
    assert body["provider_id"] == "google"
    assert body["idempotency_key"] == dispatcher.commands[0].idempotency_key


def test_replaying_a_trigger_does_not_create_a_second_run(client: TestClient) -> None:
    first = client.post("/v1/provider-checks", json=TRIGGER).json()
    second = client.post("/v1/provider-checks", json=TRIGGER).json()

    assert first["created"] is True
    assert second["created"] is False
    assert second["idempotency_key"] == first["idempotency_key"]
    assert second["run_id"] == first["run_id"]


def test_attribution_does_not_change_the_key(client: TestClient) -> None:
    first = client.post("/v1/provider-checks", json=TRIGGER).json()
    second = client.post(
        "/v1/provider-checks", json={**TRIGGER, "requested_by": "someone-else"}
    ).json()

    assert second["idempotency_key"] == first["idempotency_key"]
    assert second["created"] is False


def test_a_different_window_is_different_work(client: TestClient) -> None:
    first = client.post("/v1/provider-checks", json=TRIGGER).json()
    second = client.post(
        "/v1/provider-checks", json={**TRIGGER, "since": "2026-07-01T00:00:00Z"}
    ).json()

    assert second["idempotency_key"] != first["idempotency_key"]
    assert second["created"] is True


def test_key_is_stable_across_equivalent_timezone_spellings(client: TestClient) -> None:
    utc = client.post("/v1/provider-checks", json=TRIGGER).json()
    offset = client.post(
        "/v1/provider-checks", json={**TRIGGER, "since": "2026-08-01T02:00:00+02:00"}
    ).json()

    assert offset["idempotency_key"] == utc["idempotency_key"]


def test_naive_timestamp_is_rejected(client: TestClient) -> None:
    response = client.post("/v1/provider-checks", json={**TRIGGER, "since": "2026-08-01T00:00:00"})

    assert response.status_code == 422


def test_unknown_field_is_rejected(client: TestClient) -> None:
    response = client.post("/v1/provider-checks", json={**TRIGGER, "priority": "urgent"})

    assert response.status_code == 422


def test_trigger_fails_closed_without_a_dispatcher(unwired_client: TestClient) -> None:
    response = unwired_client.post("/v1/provider-checks", json=TRIGGER)

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "error": "dependency_unavailable",
        "dependency": "event_transport",
        "reason": "no provider-check dispatcher is configured",
    }


def test_key_derivation_is_namespaced_and_hex() -> None:
    key = provider_check_key("google", None)

    assert len(key) == 64
    assert key != provider_check_key("openai_compat", None)
