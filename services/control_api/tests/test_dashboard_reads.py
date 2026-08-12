"""The dashboard read surface.

The behaviour under test that matters most is the failure behaviour. A page
that cannot reach the read model must be told so, because an empty list and an
unreachable store look identical to a reader and mean opposite things.
"""

from fastapi.testclient import TestClient

from .conftest import FIXTURE_CHANGE_ID, FIXTURE_REPOSITORY, FIXTURE_RUN_ID

DASHBOARD_ROUTES = (
    "/v1/changes",
    f"/v1/changes/{FIXTURE_CHANGE_ID}",
    "/v1/repositories",
    "/v1/runs",
    f"/v1/runs/{FIXTURE_RUN_ID}/detail",
    "/v1/fleet",
)


def test_every_dashboard_route_fails_closed_without_a_read_model(
    unwired_client: TestClient,
) -> None:
    for route in DASHBOARD_ROUTES:
        response = unwired_client.get(route)

        assert response.status_code == 503, route
        detail = response.json()["detail"]
        assert detail["error"] == "dependency_unavailable"
        assert detail["dependency"] == "dashboard_read_model"


def test_changes_are_listed_with_their_provider_evidence(client: TestClient) -> None:
    body = client.get("/v1/changes").json()

    assert len(body["changes"]) == 1
    change = body["changes"][0]
    assert change["change_id"] == FIXTURE_CHANGE_ID
    assert change["recommended_replacement"] == "gemini-3.1-flash-image"
    # An uncaptured provider snapshot stays null rather than becoming an empty
    # string, so the dashboard cannot render it as "evidence exists".
    assert change["source_sha256"] is None
    assert change["source_urls"]


def test_unknown_change_is_not_found(client: TestClient) -> None:
    response = client.get("/v1/changes/no-such-change")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "change_not_found"


def test_repository_impact_reports_findings_and_the_commit_they_came_from(
    client: TestClient,
) -> None:
    body = client.get(f"/v1/repositories?change_id={FIXTURE_CHANGE_ID}").json()

    assert body["change_id"] == FIXTURE_CHANGE_ID
    repository = body["repositories"][0]
    assert repository["repository"] == FIXTURE_REPOSITORY
    assert repository["affected"] is True
    assert repository["usage_count"] == 1
    # Findings are attributable to a commit; a count with no SHA is unfalsifiable.
    assert repository["indexed_sha"]
    assert repository["usages"][0]["file_path"] == "cli/src/cli/cli.ts"
    assert repository["usages"][0]["detection_layer"] == "A_DETERMINISTIC"


def test_run_detail_carries_the_evidence_and_the_next_legal_states(
    client: TestClient,
) -> None:
    body = client.get(f"/v1/runs/{FIXTURE_RUN_ID}/detail").json()

    assert body["detail"]["summary"]["run_id"] == FIXTURE_RUN_ID
    assert body["terminal"] is False
    # Derived from the shared transition table, so the dashboard and the
    # orchestrator cannot disagree about what may happen next.
    assert set(body["allowed_next"]) == {"PR_CREATING", "HUMAN_REQUIRED", "FAILED"}
    assert body["detail"]["transitions"][0]["to_state"] == "RECEIVED"


def test_run_detail_never_reports_auto_merge_as_permitted(client: TestClient) -> None:
    policy = client.get(f"/v1/runs/{FIXTURE_RUN_ID}/detail").json()["detail"]["policy"]

    # Constraint 3 is surfaced, not merely enforced: the page can show the
    # boundary being kept rather than asking a reader to assume it.
    assert policy["auto_merge"] is False
    assert policy["forbidden_globs"]


def test_unknown_run_detail_is_not_found(client: TestClient) -> None:
    response = client.get("/v1/runs/run-999999999999/detail")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "run_not_found"


def test_fleet_reports_denials_against_the_actor_that_attempted_them(
    client: TestClient,
) -> None:
    body = client.get("/v1/fleet").json()

    actor = body["observed_actors"][0]
    assert actor["actor"] == "patch_agent"
    assert actor["denied"] == 1
    assert body["policy_versions"] == ["2026.08.1"]


def test_list_limits_are_bounded(client: TestClient) -> None:
    # An unbounded limit would turn a dashboard page into an export endpoint.
    assert client.get("/v1/changes?limit=0").status_code == 422
    assert client.get("/v1/changes?limit=10000").status_code == 422
