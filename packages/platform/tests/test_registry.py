"""Agent Registry client behaviour, with the HTTP layer faked.

No network. The transport is a callable the client accepts, so every case here
is an assertion about what PatchAPI sends and how it treats what comes back —
including the two failure modes that matter: a read outage must degrade, and a
write must not.
"""

import json
import logging

import pytest

from packages.platform.config import (
    DEFAULT_LOCATION,
    ENV_A2A_BASE_URL,
    ENV_ENABLED,
    ENV_LOCATION,
    ENV_MCP_URL,
    ENV_PROJECT,
    ENV_TIMEOUT,
    RegistryConfig,
    load_config,
)
from packages.platform.registry import (
    AgentRegistryClient,
    RegistryError,
    RegistryUnavailableError,
)

PROJECT = "patch-test"
PARENT = f"projects/{PROJECT}/locations/{DEFAULT_LOCATION}"


def config(**overrides) -> RegistryConfig:
    base = {"project": PROJECT, "a2a_base_url": "https://agents.example.invalid"}
    base.update(overrides)
    return RegistryConfig(**base)


class FakeTransport:
    """Answers by `(method, path-suffix)`, recording every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, body, headers):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "body": json.loads(body.decode()) if body else None,
                "headers": dict(headers),
            }
        )
        for (want_method, fragment), response in self.routes:
            if method == want_method and fragment in url:
                status, payload = response
                return status, json.dumps(payload).encode()
        raise AssertionError(f"unrouted {method} {url}")


def client(routes, **overrides) -> tuple[AgentRegistryClient, FakeTransport]:
    transport = FakeTransport(routes)
    return (
        AgentRegistryClient(
            config(**overrides),
            transport=transport,
            token_provider=lambda: "fake-token",
            sleep=lambda _seconds: None,
        ),
        transport,
    )


DONE_OPERATION = {"name": f"{PARENT}/operations/op-1", "done": True}


# -- configuration ---------------------------------------------------------


def test_config_defaults_come_from_the_environment():
    resolved = load_config(
        {
            ENV_PROJECT: " patch-505223 ",
            ENV_LOCATION: "us-central1",
            ENV_A2A_BASE_URL: "https://agents.example.invalid/",
            ENV_MCP_URL: "https://tools.example.invalid/mcp",
            ENV_TIMEOUT: "12.5",
        }
    )

    assert resolved.project == "patch-505223"
    assert resolved.location == "us-central1"
    assert resolved.enabled is True
    assert resolved.timeout_seconds == 12.5
    assert resolved.a2a_url("patch") == "https://agents.example.invalid/a2a/patch"


def test_registry_is_off_without_a_project_and_can_be_forced_off():
    assert load_config({}).enabled is False
    assert load_config({ENV_PROJECT: PROJECT, ENV_ENABLED: "0"}).enabled is False
    assert load_config({ENV_PROJECT: PROJECT, ENV_ENABLED: "false"}).enabled is False


def test_service_id_is_a_dns_name_derived_from_the_agent():
    assert config().service_id("change_intelligence") == "patchapi-agent-change-intelligence"


def test_a_missing_a2a_base_url_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match=ENV_A2A_BASE_URL):
        config(a2a_base_url=None).a2a_url("patch")


# -- reads degrade ---------------------------------------------------------


def test_list_agents_parses_skills_interfaces_and_attributes():
    registry, _ = client(
        [
            (
                ("GET", "/agents"),
                (
                    200,
                    {
                        "agents": [
                            {
                                "name": f"{PARENT}/agents/a-1",
                                "agentId": "urn:agent:x:y:patch",
                                "displayName": "PatchAPI Patch Agent",
                                "version": "1.6.0",
                                "skills": [
                                    {
                                        "id": "apply_patch",
                                        "name": "Apply patch",
                                        "description": "Apply a unified diff.",
                                        "tags": ["patchapi-fleet"],
                                    }
                                ],
                                "protocols": [
                                    {
                                        "interfaces": [
                                            {
                                                "url": "https://agents.example.invalid/a2a/patch",
                                                "protocolBinding": "JSONRPC",
                                            }
                                        ]
                                    }
                                ],
                                "attributes": {
                                    "agentregistry.googleapis.com/system/Framework": {
                                        "framework": "google-adk"
                                    }
                                },
                            }
                        ]
                    },
                ),
            )
        ]
    )

    (agent,) = registry.list_agents()
    assert agent.agent_id == "urn:agent:x:y:patch"
    assert agent.version == "1.6.0"
    assert [skill.id for skill in agent.skills] == ["apply_patch"]
    assert agent.interfaces[0].protocol_binding == "JSONRPC"
    assert agent.framework == "google-adk"


def test_list_agents_follows_pagination():
    registry, transport = client(
        [
            (("GET", "pageToken=page-2"), (200, {"agents": [{"name": "b"}]})),
            (
                ("GET", "/agents"),
                (200, {"agents": [{"name": "a"}], "nextPageToken": "page-2"}),
            ),
        ]
    )

    assert [agent.name for agent in registry.list_agents()] == ["a", "b"]
    assert len(transport.calls) == 2


def test_a_read_outage_degrades_to_empty_and_logs_why(caplog):
    def broken(_method, _url, _body, _headers):
        raise RegistryUnavailableError("connection refused")

    registry = AgentRegistryClient(config(), transport=broken, token_provider=lambda: "fake-token")

    with caplog.at_level(logging.WARNING):
        assert registry.list_agents() == ()
        assert registry.list_mcp_servers() == ()
        assert registry.list_services() == ()
        assert registry.list_bindings() == ()
        assert registry.search_agents("patch") == ()
        assert registry.get_agent(f"{PARENT}/agents/a-1") is None

    assert "connection refused" in caplog.text


def test_a_read_error_status_degrades_rather_than_raising(caplog):
    registry, _ = client(
        [
            (
                ("GET", "/agents"),
                (403, {"error": {"status": "PERMISSION_DENIED", "message": "no access"}}),
            )
        ]
    )

    with caplog.at_level(logging.WARNING):
        assert registry.list_agents() == ()

    assert "PERMISSION_DENIED" in caplog.text
    assert "no access" in caplog.text


def test_reads_are_silent_when_the_registry_is_switched_off(caplog):
    registry, transport = client([], enabled=False)

    with caplog.at_level(logging.WARNING):
        assert registry.list_agents() == ()

    assert transport.calls == []


def test_search_sends_the_query_as_a_search_string():
    registry, transport = client([(("POST", "/agents:search"), (200, {"agents": []}))])

    registry.search_agents("skills.tags:patchapi-fleet", page_size=50)

    assert transport.calls[0]["body"] == {
        "searchString": "skills.tags:patchapi-fleet",
        "pageSize": 50,
    }


def test_mcp_servers_report_their_tool_names():
    registry, _ = client(
        [
            (
                ("GET", "/mcpServers"),
                (
                    200,
                    {
                        "mcpServers": [
                            {
                                "name": f"{PARENT}/mcpServers/m-1",
                                "mcpServerId": "urn:mcp:x:y:tools",
                                "tools": [{"name": "apply_patch"}, {"name": "read_file"}],
                                "interfaces": [
                                    {"url": "https://x.invalid/mcp", "protocolBinding": "JSONRPC"}
                                ],
                            }
                        ]
                    },
                ),
            )
        ]
    )

    (server,) = registry.list_mcp_servers()
    assert server.tool_names == ("apply_patch", "read_file")
    assert server.interfaces[0].url == "https://x.invalid/mcp"


# -- writes are explicit ---------------------------------------------------


def test_register_agent_card_creates_a_service_without_interfaces():
    registry, transport = client(
        [
            (("POST", "/services?serviceId="), (200, DONE_OPERATION)),
            (
                ("GET", "/services/patchapi-agent-patch"),
                (200, {"registryResource": f"{PARENT}/agents/a-1"}),
            ),
        ]
    )

    result = registry.register_agent_card(
        service_id="patchapi-agent-patch",
        card={"name": "PatchAPI Patch Agent", "version": "1.6.0"},
        display_name="PatchAPI Patch Agent",
        description="Sandboxed migration author.",
    )

    create = transport.calls[0]
    assert create["method"] == "POST"
    assert "serviceId=patchapi-agent-patch" in create["url"]
    assert create["body"]["agentSpec"]["type"] == "A2A_AGENT_CARD"
    # An A2A_AGENT_CARD spec is rejected when the Service also sets interfaces:
    # the card's own url and preferredTransport carry connectivity.
    assert "interfaces" not in create["body"]
    assert result.created is True
    assert result.registry_resource == f"{PARENT}/agents/a-1"


def test_re_registration_patches_the_existing_service():
    registry, transport = client(
        [
            (
                ("POST", "/services?serviceId="),
                (409, {"error": {"status": "ALREADY_EXISTS", "message": "already exists"}}),
            ),
            (("PATCH", "/services/patchapi-agent-patch"), (200, DONE_OPERATION)),
            (
                ("GET", "/services/patchapi-agent-patch"),
                (200, {"registryResource": f"{PARENT}/agents/a-1"}),
            ),
        ]
    )

    result = registry.register_agent_card(
        service_id="patchapi-agent-patch",
        card={"version": "1.7.0"},
        display_name="PatchAPI Patch Agent",
        description="Sandboxed migration author.",
    )

    patch = transport.calls[1]
    assert patch["method"] == "PATCH"
    assert "updateMask=agentSpec,description,displayName" in patch["url"]
    assert result.created is False


def test_an_mcp_registration_declares_json_rpc():
    registry, transport = client(
        [
            (("POST", "/services?serviceId="), (200, DONE_OPERATION)),
            (("GET", "/services/patchapi-mcp-tools"), (200, {})),
        ]
    )

    registry.register_mcp_server(
        service_id="patchapi-mcp-tools",
        url="https://tools.example.invalid/mcp",
        tools=[{"name": "apply_patch", "description": "Apply a unified diff."}],
        display_name="PatchAPI Fleet Tools",
        description="Tool surface.",
    )

    body = transport.calls[0]["body"]
    assert body["mcpServerSpec"]["type"] == "TOOL_SPEC"
    assert body["interfaces"] == [
        {"url": "https://tools.example.invalid/mcp", "protocolBinding": "JSONRPC"}
    ]


def test_a_failed_operation_fails_the_registration():
    registry, _ = client(
        [
            (
                ("POST", "/services?serviceId="),
                (
                    200,
                    {
                        "name": f"{PARENT}/operations/op-1",
                        "done": True,
                        "error": {
                            "message": 'At /interfaces/0/protocolBinding of "HTTP_JSON"',
                        },
                    },
                ),
            )
        ]
    )

    with pytest.raises(RegistryError, match="HTTP_JSON"):
        registry.register_agent_card(
            service_id="patchapi-agent-patch",
            card={},
            display_name="x",
            description="y",
        )


def test_a_pending_operation_is_polled_until_done():
    registry, transport = client(
        [
            (
                ("POST", "/services?serviceId="),
                (200, {"name": f"{PARENT}/operations/op-1", "done": False}),
            ),
            (("GET", "/operations/op-1"), (200, DONE_OPERATION)),
            (("GET", "/services/patchapi-agent-patch"), (200, {})),
        ]
    )

    registry.register_agent_card(
        service_id="patchapi-agent-patch", card={}, display_name="x", description="y"
    )

    assert transport.calls[1]["url"].endswith("/operations/op-1")


def test_a_write_refuses_when_the_registry_is_not_configured():
    registry, transport = client([], project=None)

    with pytest.raises(ValueError, match=ENV_PROJECT):
        registry.register_agent_card(
            service_id="patchapi-agent-patch", card={}, display_name="x", description="y"
        )

    assert transport.calls == []


def test_a_write_refuses_when_the_registry_is_switched_off():
    registry, transport = client([], enabled=False)

    with pytest.raises(RegistryUnavailableError, match="disabled"):
        registry.register_agent_card(
            service_id="patchapi-agent-patch", card={}, display_name="x", description="y"
        )

    assert transport.calls == []


def test_every_request_carries_a_bearer_token():
    registry, transport = client([(("GET", "/agents"), (200, {"agents": []}))])

    registry.list_agents()

    assert transport.calls[0]["headers"]["Authorization"] == "Bearer fake-token"
