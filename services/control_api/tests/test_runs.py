from fastapi.testclient import TestClient


def test_run_state_read_reports_the_stored_row(client: TestClient, run_record) -> None:
    response = client.get(f"/v1/runs/{run_record.run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_record.run_id
    assert body["state"] == "VERIFYING"
    assert body["repository"] == run_record.repository
    assert body["base_sha"] == run_record.base_sha


def test_allowed_next_comes_from_the_shared_transition_table(
    client: TestClient, run_record
) -> None:
    body = client.get(f"/v1/runs/{run_record.run_id}").json()

    # VERIFYING may only advance to PR creation, escalate to a human, or fail.
    # No path from VERIFYING skips the independent verification result.
    assert body["allowed_next"] == [
        "FAILED",
        "HUMAN_REQUIRED",
        "PR_CREATING",
        "WAITING_ON_OPERATOR",
    ]
    assert body["terminal"] is False


def test_unknown_run_is_a_structured_404(client: TestClient) -> None:
    response = client.get("/v1/runs/run-999999999999")

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "error": "run_not_found",
        "run_id": "run-999999999999",
    }


def test_read_fails_closed_without_a_state_store(unwired_client: TestClient, run_record) -> None:
    response = unwired_client.get(f"/v1/runs/{run_record.run_id}")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "error": "dependency_unavailable",
        "dependency": "workflow_state_store",
        "reason": "no authoritative run-state reader is configured",
    }
