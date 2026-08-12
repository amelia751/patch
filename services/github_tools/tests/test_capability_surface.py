"""The surface is exactly the roadmap §7.3 allowlist, and nothing else.

These are the tests that would fail if someone widened the service: a new
operation that is not in the shared enum, a merge route, a DELETE, or a URL
shape that reaches administration or secrets.
"""

import inspect

import pytest
from patchapi_github_tools import github_rest
from patchapi_github_tools.app import create_app
from patchapi_github_tools.github_rest import ForbiddenEndpointError, _assert_permitted
from patchapi_github_tools.operations import REGISTRY

from packages.github import FORBIDDEN_CAPABILITIES, Capability

# The read and write operations roadmap §7.3 lists, verbatim.
EXPECTED_CAPABILITIES = {
    "get_repository_metadata",
    "get_file",
    "list_tree",
    "get_commit",
    "get_pull_request",
    "get_checks",
    "create_patch_branch",
    "commit_verified_patch",
    "open_pull_request",
    "add_pr_comment",
}


def test_registry_matches_the_shared_allowlist_exactly():
    assert set(REGISTRY) == set(Capability)
    assert {capability.value for capability in REGISTRY} == EXPECTED_CAPABILITIES


def test_no_forbidden_capability_is_implemented():
    implemented = {capability.value for capability in REGISTRY}
    assert implemented.isdisjoint(FORBIDDEN_CAPABILITIES)


def test_routes_are_only_health_and_the_capability_choke_point():
    paths = {route.path for route in create_app().routes if hasattr(route, "path")}
    product_paths = {path for path in paths if not path.startswith(("/docs", "/redoc", "/openapi"))}
    assert product_paths == {
        "/healthz",
        "/readyz",
        "/v1/capabilities",
        "/v1/capabilities/{capability_name}",
    }


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_CAPABILITIES))
def test_no_route_or_handler_is_named_after_a_forbidden_operation(forbidden):
    names = {route.name for route in create_app().routes if hasattr(route, "name")}
    assert forbidden not in names
    assert not hasattr(github_rest.GitHubRest, forbidden)


@pytest.mark.parametrize(
    "path",
    [
        "/repos/o/r/pulls/7/merge",
        "/repos/o/r/merges",
        "/repos/o/r/merge-upstream",
        "/repos/o/r/branches/main/protection",
        "/repos/o/r/rulesets/12",
        "/repos/o/r/actions/secrets/DEPLOY_KEY",
        "/repos/o/r/actions/variables/X",
        "/repos/o/r/dependabot/secrets/X",
        "/repos/o/r/environments/prod/secrets/X",
        "/repos/o/r/collaborators/someone",
        "/orgs/o/teams/admins",
        "/repos/o/r/pulls/7/reviews",
        "/repos/o/r/contents/.github/workflows/release.yml",
    ],
)
def test_transport_refuses_forbidden_url_shapes(path):
    with pytest.raises(ForbiddenEndpointError):
        _assert_permitted("POST", path)


@pytest.mark.parametrize("method", ["DELETE", "PUT", "HEAD", "OPTIONS"])
def test_transport_refuses_methods_outside_the_surface(method):
    with pytest.raises(ForbiddenEndpointError):
        _assert_permitted(method, "/repos/o/r")


def test_transport_permits_the_endpoints_the_surface_needs():
    for method, path in (
        ("GET", "/repos/o/r"),
        ("POST", "/repos/o/r/git/refs"),
        ("PATCH", "/repos/o/r/git/refs/heads/patchapi/migrate"),
        ("POST", "/repos/o/r/pulls"),
        ("PATCH", "/repos/o/r/pulls/3"),
    ):
        _assert_permitted(method, path)


def test_every_operation_handler_is_reachable_only_through_the_registry():
    # A handler that is not registered would be dead code that a future route
    # could pick up without passing the identity and grant checks.
    from patchapi_github_tools import operations

    registered = {operation.handler for operation in REGISTRY.values()}
    public_coroutines = {
        function
        for name, function in vars(operations).items()
        if inspect.iscoroutinefunction(function) and not name.startswith("_")
    }
    assert public_coroutines == registered


def test_catalog_advertises_the_boundary(client):
    body = client.get("/v1/capabilities").json()
    assert {entry["name"] for entry in body["exposed"]} == EXPECTED_CAPABILITIES
    assert set(body["never_exposed"]) == set(FORBIDDEN_CAPABILITIES)
    assert "stops at the pull request" in body["automation_boundary"]
    # Roadmap §8.1: the agent that reads untrusted provider material holds no
    # repository capability at all.
    assert body["grants"]["patchapi.change_intelligence"] == []
