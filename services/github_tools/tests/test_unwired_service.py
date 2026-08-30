"""With no GitHub App configured the service is honest and inert.

This is the state the fleet runs in until the App is provisioned: everything
that describes the surface works, everything that would touch GitHub returns a
503 naming the missing dependency. Nothing pretends to have succeeded.
"""

import pytest

from packages.github import Capability


def test_healthz_is_ok_without_credentials(unwired_client):
    body = unwired_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["service"] == "patchapi-github-tools"


def test_readyz_is_not_ready_and_says_why(unwired_client):
    response = unwired_client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    check = body["checks"][0]
    assert check["name"] == "github_app_installation"
    assert check["ready"] is False
    assert "credentials" in check["reason"]


def test_the_catalog_is_served_without_credentials(unwired_client):
    body = unwired_client.get("/v1/capabilities").json()
    assert len(body["exposed"]) == len(Capability)


@pytest.mark.parametrize("capability", sorted(item.value for item in Capability))
def test_every_capability_fails_closed_without_credentials(unwired_client, capability):
    response = unwired_client.post(
        f"/v1/capabilities/{capability}",
        json={"repo": "amelia751/egaki"},
        headers={"X-PatchAPI-Agent": "patchapi.pr"},
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "dependency_unavailable"
    assert detail["dependency"] == "github_app_installation"
    assert "no GitHub call was attempted" in detail["reason"]


def test_a_forbidden_capability_is_still_refused_as_forbidden(unwired_client):
    # The boundary does not depend on credentials being present.
    response = unwired_client.post(
        "/v1/capabilities/merge_pull_request",
        json={},
        headers={"X-PatchAPI-Agent": "patchapi.pr"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "forbidden_capability"


def test_openapi_describes_the_whole_surface(unwired_client):
    document = unwired_client.get("/openapi.json").json()
    assert set(document["paths"]) == {
        "/healthz",
        "/readyz",
        "/mcp",
        "/v1/capabilities",
        "/v1/capabilities/{capability_name}",
    }
    served = json_dump(document)
    for forbidden in ("merge", "protection", "admin", "secrets"):
        assert f"/{forbidden}" not in served


def json_dump(document: dict) -> str:
    import json

    return json.dumps(document["paths"])
