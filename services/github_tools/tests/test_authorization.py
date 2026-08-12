"""Identity, allowlist, and grants — in that order, before GitHub is touched.

Every refusal here must be structured and must leave `fake_github.calls` empty:
a rejected request that still reached GitHub would mean the boundary is advisory.
"""

import pytest

from packages.github import FORBIDDEN_CAPABILITIES


def only_token_calls(fake_github) -> bool:
    """True when nothing but installation-token minting reached GitHub."""
    return all("access_tokens" in path for _method, path in fake_github.calls)


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_CAPABILITIES))
def test_forbidden_capability_is_refused_with_a_structured_403(
    client, fake_github, pr_headers, forbidden
):
    response = client.post(
        f"/v1/capabilities/{forbidden}", json={"repo": "amelia751/egaki"}, headers=pr_headers
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "forbidden_capability"
    assert detail["capability"] == forbidden
    assert "stops at the pull request" in detail["reason"]
    assert only_token_calls(fake_github)


def test_forbidden_capability_is_refused_even_for_a_read_only_agent(
    client, fake_github, impact_headers
):
    response = client.post(
        "/v1/capabilities/merge_pull_request",
        json={"repo": "amelia751/egaki", "number": 1},
        headers=impact_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "forbidden_capability"
    assert only_token_calls(fake_github)


def test_capability_name_is_normalised_before_it_is_refused(client, pr_headers):
    response = client.post("/v1/capabilities/%20MERGE_PULL_REQUEST%20", json={}, headers=pr_headers)
    assert response.status_code == 403
    assert response.json()["detail"]["capability"] == "merge_pull_request"


def test_unknown_capability_is_a_structured_404(client, fake_github, pr_headers):
    response = client.post("/v1/capabilities/rm_minus_rf", json={}, headers=pr_headers)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "unknown_capability"
    assert "get_file" in detail["exposed_capabilities"]
    assert only_token_calls(fake_github)


def test_missing_agent_identity_is_401(client, fake_github):
    response = client.post(
        "/v1/capabilities/get_repository_metadata", json={"repo": "amelia751/egaki"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "unknown_agent"
    assert only_token_calls(fake_github)


def test_unrecognised_agent_is_401(client, fake_github):
    response = client.post(
        "/v1/capabilities/get_repository_metadata",
        json={"repo": "amelia751/egaki"},
        headers={"X-PatchAPI-Agent": "attacker.agent"},
    )
    assert response.status_code == 401
    assert only_token_calls(fake_github)


@pytest.mark.parametrize(
    "capability",
    ["create_patch_branch", "commit_verified_patch", "open_pull_request", "add_pr_comment"],
)
def test_read_only_agent_cannot_reach_a_write_capability(
    client, fake_github, impact_headers, capability
):
    response = client.post(
        f"/v1/capabilities/{capability}", json={"repo": "amelia751/egaki"}, headers=impact_headers
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "capability_not_granted"
    assert detail["agent"] == "patchapi.impact"
    assert capability not in detail["granted_capabilities"]
    assert only_token_calls(fake_github)


def test_change_intelligence_agent_holds_no_repository_grant(client, fake_github):
    response = client.post(
        "/v1/capabilities/get_file",
        json={"repo": "amelia751/egaki", "path": "README.md", "ref": "a" * 40},
        headers={"X-PatchAPI-Agent": "patchapi.change_intelligence"},
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "capability_not_granted"
    assert detail["granted_capabilities"] == []
    assert only_token_calls(fake_github)


def test_bad_arguments_are_refused_before_github_is_called(client, fake_github, impact_headers):
    response = client.post(
        "/v1/capabilities/get_file",
        json={"repo": "amelia751/egaki", "path": "README.md", "ref": "main"},
        headers=impact_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_arguments"
    assert only_token_calls(fake_github)


def test_write_outside_the_patch_branch_prefix_is_refused(client, fake_github, pr_headers):
    response = client.post(
        "/v1/capabilities/create_patch_branch",
        json={"repo": "amelia751/egaki", "branch": "main", "base_sha": "a" * 40},
        headers=pr_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_arguments"
    assert only_token_calls(fake_github)


def test_unexpected_argument_is_refused(client, impact_headers):
    response = client.post(
        "/v1/capabilities/get_commit",
        json={"repo": "amelia751/egaki", "sha": "a" * 40, "force": True},
        headers=impact_headers,
    )
    assert response.status_code == 422
