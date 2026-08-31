"""The MCP transport is discovery, not privilege.

Every test here exists to prove one of two things: that the tool descriptors
describe the real surface, and that `tools/call` is refused by exactly the gates
`/v1/capabilities/{name}` is refused by. A refusal must also leave
`fake_github.calls` empty apart from token minting — an MCP request that reached
GitHub before being refused would mean the second transport is a way around the
boundary rather than a view onto it.
"""

import json

import pytest
from patchapi_github_tools.config import (
    MCP_PROTOCOL_VERSION,
    SERVICE_NAME,
    SERVICE_VERSION,
)
from patchapi_github_tools.mcp_catalog import input_schema
from patchapi_github_tools.models import OpenPullRequestArgs
from patchapi_github_tools.operations import REGISTRY

from packages.github import FORBIDDEN_CAPABILITIES, READ_CAPABILITIES, Capability

WRITE_TOOLS = [
    "create_patch_branch",
    "commit_verified_patch",
    "open_pull_request",
    "add_pr_comment",
]


def only_token_calls(fake_github) -> bool:
    """True when nothing but installation-token minting reached GitHub."""
    return all("access_tokens" in path for _method, path in fake_github.calls)


def rpc(client, method, params=None, *, headers, request_id=1):
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers)


def result_of(response) -> dict:
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "error" not in payload, payload
    return payload["result"]


def error_of(response) -> dict:
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "result" not in payload, payload
    return payload["error"]


# --- handshake ------------------------------------------------------------


def test_initialize_reports_the_pinned_service_identity(client, impact_headers):
    result = result_of(
        rpc(client, "initialize", {"protocolVersion": "2025-06-18"}, headers=impact_headers)
    )
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert result["serverInfo"] == {"name": SERVICE_NAME, "version": SERVICE_VERSION}
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert "stops at the pull request" in result["instructions"]


def test_initialize_echoes_an_older_accepted_revision(client, impact_headers):
    result = result_of(
        rpc(client, "initialize", {"protocolVersion": "2024-11-05"}, headers=impact_headers)
    )
    assert result["protocolVersion"] == "2024-11-05"


def test_initialize_falls_back_for_an_unrecognised_revision(client, impact_headers):
    result = result_of(
        rpc(client, "initialize", {"protocolVersion": "1999-01-01"}, headers=impact_headers)
    )
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION


def test_ping_is_an_empty_result(client, impact_headers):
    assert result_of(rpc(client, "ping", headers=impact_headers)) == {}


def test_initialized_notification_is_accepted_without_a_response(client, impact_headers):
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=impact_headers,
    )
    assert response.status_code == 202
    assert not response.content


# --- the catalog ----------------------------------------------------------


def test_tools_list_never_names_a_forbidden_operation(client, pr_headers):
    names = {
        tool["name"] for tool in result_of(rpc(client, "tools/list", headers=pr_headers))["tools"]
    }
    assert names.isdisjoint(FORBIDDEN_CAPABILITIES)
    assert names == {capability.value for capability in REGISTRY}


def test_tools_list_is_scoped_to_the_calling_identity(client, pr_headers, impact_headers):
    pr_tools = {
        tool["name"] for tool in result_of(rpc(client, "tools/list", headers=pr_headers))["tools"]
    }
    impact_tools = {
        tool["name"]
        for tool in result_of(rpc(client, "tools/list", headers=impact_headers))["tools"]
    }
    assert set(WRITE_TOOLS) <= pr_tools
    assert impact_tools == {capability.value for capability in READ_CAPABILITIES}
    assert impact_tools.isdisjoint(WRITE_TOOLS)


def test_change_intelligence_agent_sees_an_empty_catalog(client):
    # Roadmap §8.1: it reads untrusted provider material and holds no grant, so
    # the catalog must not even advertise a repository operation to it.
    result = result_of(
        rpc(client, "tools/list", headers={"X-PatchAPI-Agent": "patchapi.change_intelligence"})
    )
    assert result["tools"] == []


def test_annotations_declare_read_only_and_non_destructive(client, pr_headers):
    tools = {
        tool["name"]: tool
        for tool in result_of(rpc(client, "tools/list", headers=pr_headers))["tools"]
    }
    for capability in Capability:
        annotations = tools[capability.value]["annotations"]
        assert annotations["readOnlyHint"] is (capability in READ_CAPABILITIES)
        assert annotations["destructiveHint"] is False
        assert annotations["openWorldHint"] is True
        assert annotations["title"] == REGISTRY[capability].summary


@pytest.mark.parametrize(
    ("name", "idempotent"),
    [
        ("get_file", True),
        ("create_patch_branch", True),
        ("open_pull_request", True),
        ("commit_verified_patch", False),
        ("add_pr_comment", False),
    ],
)
def test_idempotency_hints_match_the_handlers(client, pr_headers, name, idempotent):
    tools = {
        tool["name"]: tool
        for tool in result_of(rpc(client, "tools/list", headers=pr_headers))["tools"]
    }
    assert tools[name]["annotations"]["idempotentHint"] is idempotent


def test_input_schemas_come_from_the_request_models(client, pr_headers):
    tools = {
        tool["name"]: tool
        for tool in result_of(rpc(client, "tools/list", headers=pr_headers))["tools"]
    }
    for capability, operation in REGISTRY.items():
        published = tools[capability.value]["inputSchema"]
        expected = operation.args_model.model_json_schema()
        assert set(published["properties"]) == set(expected["properties"])
        assert published.get("required", []) == expected.get("required", [])
        assert published["additionalProperties"] is False


def test_published_schemas_carry_no_json_schema_references(client, pr_headers):
    tools = result_of(rpc(client, "tools/list", headers=pr_headers))["tools"]
    serialized = json.dumps(tools)
    assert "$ref" not in serialized
    assert "$defs" not in serialized


def test_nested_models_are_inlined_rather_than_dropped():
    schema = input_schema(OpenPullRequestArgs)
    evidence = schema["properties"]["evidence"]
    assert "risk_level" in evidence["properties"]
    assert "$ref" not in json.dumps(evidence)


# --- authorization: the same gates, in the same order ---------------------


def test_missing_agent_identity_is_401_before_any_envelope_is_parsed(client, fake_github):
    response = client.post("/mcp", content=b"not json at all")
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "unknown_agent"
    assert only_token_calls(fake_github)


def test_unrecognised_agent_is_401(client, fake_github):
    response = rpc(client, "tools/list", headers={"X-PatchAPI-Agent": "attacker.agent"})
    assert response.status_code == 401
    assert only_token_calls(fake_github)


@pytest.mark.parametrize("capability", WRITE_TOOLS)
def test_read_only_agent_cannot_call_a_write_tool(client, fake_github, impact_headers, capability):
    error = error_of(
        rpc(
            client,
            "tools/call",
            {"name": capability, "arguments": {"repo": "amelia751/storygen"}},
            headers=impact_headers,
        )
    )
    assert error["code"] == -32002
    assert error["data"]["error"] == "capability_not_granted"
    assert error["data"]["agent"] == "patchapi.impact"
    assert capability not in error["data"]["granted_capabilities"]
    assert error["data"]["http_status"] == 403
    assert only_token_calls(fake_github)


def test_change_intelligence_agent_cannot_call_a_read_tool(client, fake_github):
    error = error_of(
        rpc(
            client,
            "tools/call",
            {
                "name": "get_file",
                "arguments": {"repo": "amelia751/storygen", "path": "a", "ref": "a" * 40},
            },
            headers={"X-PatchAPI-Agent": "patchapi.change_intelligence"},
        )
    )
    assert error["code"] == -32002
    assert error["data"]["granted_capabilities"] == []
    assert only_token_calls(fake_github)


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_CAPABILITIES))
def test_forbidden_operation_is_refused_with_its_own_code(
    client, fake_github, pr_headers, forbidden
):
    error = error_of(
        rpc(client, "tools/call", {"name": forbidden, "arguments": {}}, headers=pr_headers)
    )
    assert error["code"] == -32001
    assert error["data"]["error"] == "forbidden_capability"
    assert error["data"]["capability"] == forbidden
    assert "stops at the pull request" in error["data"]["reason"]
    assert only_token_calls(fake_github)


def test_a_forbidden_name_is_distinguishable_from_an_unknown_one(client, fake_github, pr_headers):
    forbidden = error_of(
        rpc(client, "tools/call", {"name": "merge_pull_request"}, headers=pr_headers)
    )
    unknown = error_of(rpc(client, "tools/call", {"name": "rm_minus_rf"}, headers=pr_headers))
    assert forbidden["code"] == -32001
    assert unknown["code"] == -32602
    assert forbidden["code"] != unknown["code"]
    assert forbidden["data"]["error"] == "forbidden_capability"
    assert unknown["data"]["error"] == "unknown_capability"
    assert only_token_calls(fake_github)


def test_capability_name_is_normalised_before_it_is_refused(client, pr_headers):
    error = error_of(
        rpc(client, "tools/call", {"name": "  MERGE_PULL_REQUEST "}, headers=pr_headers)
    )
    assert error["data"]["capability"] == "merge_pull_request"


def test_bad_arguments_are_refused_before_github_is_called(client, fake_github, impact_headers):
    error = error_of(
        rpc(
            client,
            "tools/call",
            {
                "name": "get_file",
                "arguments": {"repo": "amelia751/storygen", "path": "a", "ref": "main"},
            },
            headers=impact_headers,
        )
    )
    assert error["code"] == -32602
    assert error["data"]["error"] == "invalid_arguments"
    assert only_token_calls(fake_github)


def test_a_granted_call_fails_closed_without_credentials(unwired_client, impact_headers):
    error = error_of(
        rpc(
            unwired_client,
            "tools/call",
            {"name": "get_repository_metadata", "arguments": {"repo": "amelia751/storygen"}},
            headers=impact_headers,
        )
    )
    assert error["code"] == -32003
    assert error["data"]["error"] == "dependency_unavailable"
    assert "no GitHub call was attempted" in error["data"]["reason"]


def test_a_granted_call_returns_the_same_envelope_as_the_rest_route(client, impact_headers):
    arguments = {"repo": "amelia751/storygen"}
    rest = client.post(
        "/v1/capabilities/get_repository_metadata", json=arguments, headers=impact_headers
    )
    assert rest.status_code == 200
    result = result_of(
        rpc(
            client,
            "tools/call",
            {"name": "get_repository_metadata", "arguments": arguments},
            headers=impact_headers,
        )
    )
    assert result["isError"] is False
    assert result["structuredContent"] == rest.json()
    assert json.loads(result["content"][0]["text"]) == rest.json()


def test_no_response_body_contains_an_installation_token(client, pr_headers):
    for response in (
        rpc(client, "initialize", headers=pr_headers),
        rpc(client, "tools/list", headers=pr_headers),
        rpc(
            client,
            "tools/call",
            {"name": "get_repository_metadata", "arguments": {"repo": "amelia751/storygen"}},
            headers=pr_headers,
        ),
    ):
        assert "ghs_" not in response.text
        assert "Authorization" not in response.text


# --- protocol framing -----------------------------------------------------


def test_malformed_json_is_a_parse_error(client, impact_headers):
    response = client.post("/mcp", content=b"{not json", headers=impact_headers)
    error = error_of(response)
    assert error["code"] == -32700


def test_a_non_object_envelope_is_an_invalid_request(client, impact_headers):
    error = error_of(client.post("/mcp", json="tools/list", headers=impact_headers))
    assert error["code"] == -32600


def test_a_batch_is_refused_as_an_invalid_request(client, impact_headers):
    error = error_of(
        client.post(
            "/mcp",
            json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}],
            headers=impact_headers,
        )
    )
    assert error["code"] == -32600
    assert "batch" in error["message"]


@pytest.mark.parametrize(
    "envelope",
    [
        {"id": 1, "method": "ping"},
        {"jsonrpc": "1.0", "id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "id": 1},
        {"jsonrpc": "2.0", "id": 1, "method": ""},
        {"jsonrpc": "2.0", "id": {"nested": True}, "method": "ping"},
        {"jsonrpc": "2.0", "id": True, "method": "ping"},
    ],
)
def test_a_broken_envelope_is_an_invalid_request(client, impact_headers, envelope):
    error = error_of(client.post("/mcp", json=envelope, headers=impact_headers))
    assert error["code"] == -32600


def test_a_determinable_id_survives_an_invalid_request(client, impact_headers):
    error_response = client.post(
        "/mcp", json={"jsonrpc": "1.0", "id": "abc-123", "method": "ping"}, headers=impact_headers
    )
    assert error_of(error_response)["code"] == -32600
    assert error_response.json()["id"] == "abc-123"


def test_an_unsupported_method_is_method_not_found(client, impact_headers):
    error = error_of(rpc(client, "resources/list", headers=impact_headers))
    assert error["code"] == -32601


@pytest.mark.parametrize("params", ["a string", 7, [1, 2]])
def test_non_object_params_are_invalid_params(client, impact_headers, params):
    error = error_of(
        client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params},
            headers=impact_headers,
        )
    )
    assert error["code"] == -32602


@pytest.mark.parametrize(
    "params", [{}, {"name": ""}, {"name": 7}, {"name": "get_file", "arguments": 3}]
)
def test_a_malformed_tools_call_is_invalid_params(client, impact_headers, params):
    error = error_of(rpc(client, "tools/call", params, headers=impact_headers))
    assert error["code"] == -32602


def test_the_request_id_is_echoed(client, impact_headers):
    response = rpc(client, "ping", headers=impact_headers, request_id="abc-123")
    assert response.json()["id"] == "abc-123"
