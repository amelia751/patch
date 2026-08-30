"""Pinned Agent Registry configuration.

Every host, API version, resource-id prefix and environment-variable name the
registry client depends on is declared here. Call sites take a `RegistryConfig`;
none of them names a project, a region or a URL (CLAUDE.md: pins live in
configuration, never inlined at a call site).

The registry is a *catalog*, not a control plane. Nothing in a remediation run
reads from it to make a decision, which is why `enabled` defaults to "on when a
project is configured" and every read degrades instead of raising: a registry
outage must cost the fleet its listing, not its run.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

# Bumped when the shape of the cards this package publishes changes, so a
# catalog entry can be traced to the code that produced it.
CATALOG_VERSION: Final[str] = "1.0.0"

REGISTRY_HOST: Final[str] = "https://agentregistry.googleapis.com"
REGISTRY_API_VERSION: Final[str] = "v1"
REGISTRY_SCOPES: Final[tuple[str, ...]] = ("https://www.googleapis.com/auth/cloud-platform",)

# Agent Registry is regional and, unlike the Gemini 3.x model endpoints, has no
# `global` location. Probed 2026-08-30 on project patch-505223: `us-central1` is
# the location where `projects.locations.services.create` succeeds and where the
# project's Vertex reasoning engines are auto-discovered, so the catalog and the
# runtime it describes stay in one region.
DEFAULT_LOCATION: Final[str] = "us-central1"

ENV_PROJECT: Final[str] = "GCP_PROJECT"
ENV_LOCATION: Final[str] = "PATCHAPI_REGISTRY_LOCATION"
ENV_ENABLED: Final[str] = "PATCHAPI_REGISTRY_ENABLED"
ENV_A2A_BASE_URL: Final[str] = "PATCHAPI_A2A_BASE_URL"
ENV_MCP_URL: Final[str] = "PATCHAPI_MCP_URL"
ENV_TIMEOUT: Final[str] = "PATCHAPI_REGISTRY_TIMEOUT_SECONDS"

# One registry Service per fleet agent, named after the agent. The prefix keeps
# PatchAPI's entries distinguishable from the Workspace and reasoning-engine
# agents Google auto-discovers into the same project catalog.
SERVICE_ID_PREFIX: Final[str] = "patchapi-agent-"

# The *fleet's* MCP tool surface — the agents' own tools — registered only once
# a JSON-RPC endpoint serves them (see `Interface.protocolBinding` below).
#
# `ENV_MCP_URL` must name that endpoint and no other. The GitHub capability
# adapter also speaks MCP, but it serves a different tool list; pointing this at
# it would publish a catalog entry whose advertised tools the endpoint does not
# have. A different surface is a different Service.
MCP_SERVICE_ID: Final[str] = "patchapi-mcp-tools"

# `AgentSpec.type` / `McpServerSpec.type` from the v1 discovery document.
SPEC_A2A_AGENT_CARD: Final[str] = "A2A_AGENT_CARD"
SPEC_MCP_TOOL_SPEC: Final[str] = "TOOL_SPEC"

# `Interface.protocolBinding`. An MCP Server registration is rejected by the
# create operation with anything but JSONRPC — a REST tool service cannot be
# registered as an MCP server, only a real JSON-RPC `/mcp` endpoint can.
PROTOCOL_BINDING_JSONRPC: Final[str] = "JSONRPC"

# A2A protocol version the published cards declare.
A2A_PROTOCOL_VERSION: Final[str] = "0.3.0"

# Path each agent's A2A card points at, under the agent runtime's base URL.
A2A_PATH_PREFIX: Final[str] = "/a2a"

A2A_INPUT_MODES: Final[tuple[str, ...]] = ("application/json",)
A2A_OUTPUT_MODES: Final[tuple[str, ...]] = ("application/json",)

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

# `services.create` returns a long-running operation; the Agent resource only
# appears once it is done. Observed completion is sub-second, so a short poll
# with a bounded wait is enough and a stuck operation is reported, not awaited
# forever.
OPERATION_POLL_INTERVAL_SECONDS: Final[float] = 1.0
OPERATION_TIMEOUT_SECONDS: Final[float] = 120.0

# `services.list` and `agents.list` cap the page at 100 regardless of request.
PAGE_SIZE: Final[int] = 100


@dataclass(frozen=True, slots=True)
class RegistryConfig:
    """Resolved pins for one Agent Registry session.

    `project` stays optional so the client is constructible with no GCP context
    at all; the reads report "not configured" and the writes refuse.
    """

    project: str | None = None
    location: str = DEFAULT_LOCATION
    enabled: bool = True
    a2a_base_url: str | None = None
    mcp_url: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def configured(self) -> bool:
        """Whether reads and writes may be attempted at all."""
        return self.enabled and bool(self.project)

    @property
    def parent(self) -> str:
        """`projects/{p}/locations/{l}`, the parent of every registry collection."""
        return f"projects/{self.require_project()}/locations/{self.location}"

    def require_project(self) -> str:
        if not self.project:
            raise ValueError(f"no GCP project configured; set {ENV_PROJECT} (see .env.example)")
        return self.project

    def collection_url(self, collection: str) -> str:
        """Full URL for one collection under this project and location."""
        return f"{REGISTRY_HOST}/{REGISTRY_API_VERSION}/{self.parent}/{collection}"

    def resource_url(self, name: str) -> str:
        """Full URL for a resource named relative to the API root.

        Accepts the `projects/.../operations/...` form every long-running
        operation and every list entry reports itself as.
        """
        return f"{REGISTRY_HOST}/{REGISTRY_API_VERSION}/{name.lstrip('/')}"

    def service_id(self, agent: str) -> str:
        """Registry Service id for a fleet agent name."""
        return f"{SERVICE_ID_PREFIX}{agent.replace('_', '-')}"

    def a2a_url(self, agent: str) -> str:
        """The A2A endpoint an agent's card advertises."""
        base = (self.a2a_base_url or "").rstrip("/")
        if not base:
            raise ValueError(
                f"no A2A base URL configured; set {ENV_A2A_BASE_URL} to the agent "
                "runtime's origin (scripts/register_agent_registry.sh resolves it)"
            )
        return f"{base}{A2A_PATH_PREFIX}/{agent}"


def _flag(raw: str, *, default: bool) -> bool:
    value = raw.strip().lower()
    if not value:
        return default
    return value not in {"0", "false", "no", "off"}


def load_config(environ: Mapping[str, str] | None = None) -> RegistryConfig:
    """Build a config from the environment.

    `enabled` follows the project when the flag is unset: a developer with no
    `GCP_PROJECT` gets no registry traffic, and a deployment that has one gets
    its catalog without a second variable to remember.
    """
    env = os.environ if environ is None else environ
    project = env.get(ENV_PROJECT, "").strip() or None

    raw_timeout = env.get(ENV_TIMEOUT, "").strip()
    try:
        timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    if timeout <= 0:
        timeout = DEFAULT_TIMEOUT_SECONDS

    return RegistryConfig(
        project=project,
        location=env.get(ENV_LOCATION, "").strip() or DEFAULT_LOCATION,
        enabled=_flag(env.get(ENV_ENABLED, ""), default=project is not None),
        a2a_base_url=env.get(ENV_A2A_BASE_URL, "").strip() or None,
        mcp_url=env.get(ENV_MCP_URL, "").strip() or None,
        timeout_seconds=timeout,
    )
