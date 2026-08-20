from fastapi.testclient import TestClient
from patchapi_control_api.config import SERVICE_NAME, SERVICE_VERSION
from patchapi_control_api.ports import ReadinessProbe


def test_healthz_is_ok_without_any_dependency(unwired_client: TestClient) -> None:
    response = unwired_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "environment": "local",
    }


def test_health_matches_healthz(unwired_client: TestClient) -> None:
    """Cloud Run's frontend intercepts `/healthz`; `/health` is the public alias."""
    assert unwired_client.get("/health").json() == unwired_client.get("/healthz").json()


def test_readyz_fails_closed_when_dependencies_are_missing(unwired_client: TestClient) -> None:
    response = unwired_client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    not_ready = {check["name"] for check in body["checks"] if not check["ready"]}
    assert not_ready == {"event_transport", "workflow_state_store", "dashboard_read_model"}


def test_readyz_is_ready_once_every_port_is_wired(client: TestClient) -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readyz_reports_a_raising_probe_as_not_ready() -> None:
    from patchapi_control_api.app import create_app

    async def explode() -> str | None:
        raise ConnectionRefusedError("postgres://user:pw@host/db")

    app = create_app(extra_probes=[ReadinessProbe(name="exploding", check=explode)])
    response = TestClient(app, raise_server_exceptions=False).get("/readyz")

    assert response.status_code == 503
    check = next(c for c in response.json()["checks"] if c["name"] == "exploding")
    # The DSN in the exception message must not reach the readiness payload.
    assert check == {
        "name": "exploding",
        "ready": False,
        "detail": "probe raised ConnectionRefusedError",
    }


def test_cors_preflight_allows_patch() -> None:
    """Configure → Connection uses PATCH /cloud-provider. JetRun allows all
    methods; omitting PATCH here makes the browser report Failed to fetch.
    """
    from patchapi_control_api.app import create_app

    app = create_app(allowed_origins=["http://localhost:3000"])
    response = TestClient(app).options(
        "/api/projects/example/cloud-provider",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    allowed = response.headers.get("access-control-allow-methods", "")
    assert "PATCH" in allowed.upper()


def test_openapi_document_describes_the_whole_surface(unwired_client: TestClient) -> None:
    document = unwired_client.get("/openapi.json").json()

    assert set(document["paths"]) == {
        "/health",
        "/healthz",
        "/readyz",
        "/v1/provider-checks",
        "/v1/runs",
        "/v1/runs/{run_id}",
        "/v1/runs/{run_id}/detail",
        "/v1/changes",
        "/v1/changes/{change_id}",
        "/v1/repositories",
        "/v1/fleet",
        "/v1/github/webhooks",
    }
    assert document["info"]["version"] == SERVICE_VERSION
