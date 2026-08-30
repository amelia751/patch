"""Google Agent Registry client (roadmap §12.1).

The registry is where an enterprise finds out which agents exist, what each one
claims it can do, and what identity it runs as. PatchAPI publishes its fleet
there so the catalog is a property of the deployment rather than a slide.

Two rules shape this module.

*Reads are fail-soft.* A remediation run must never fail because a catalog was
unreachable. `list_agents`, `get_agent`, `search_agents`, `list_mcp_servers`,
`list_services` and `list_bindings` return empty or `None` and log the reason.
Nothing in the run path branches on their result.

*Writes are explicit.* `register_service` raises. Registration happens in a
script an operator runs, where a failure has to be visible and fixed, and a
half-published catalog is worse than an unpublished one.

Transport is `urllib` behind an injectable callable, and credentials come from
`google.auth`. There is no client library dependency to keep in step with the
API, and tests fake the transport rather than the network.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from packages.platform.config import (
    OPERATION_POLL_INTERVAL_SECONDS,
    OPERATION_TIMEOUT_SECONDS,
    PAGE_SIZE,
    PROTOCOL_BINDING_JSONRPC,
    REGISTRY_SCOPES,
    SPEC_A2A_AGENT_CARD,
    SPEC_MCP_TOOL_SPEC,
    RegistryConfig,
    load_config,
)

log = logging.getLogger(__name__)

# `(method, url, body, headers) -> (status, payload)`. A 4xx or 5xx is returned,
# not raised: the client decides which statuses are outcomes (409 on create) and
# which are failures.
Transport = Callable[[str, str, bytes | None, Mapping[str, str]], tuple[int, bytes]]

_JSON: Final[str] = "application/json"


class RegistryError(RuntimeError):
    """A registry write did not take effect."""


class RegistryUnavailableError(RegistryError):
    """The registry could not be reached, or is not configured.

    Reads catch this and degrade. Writes let it out: an operator running the
    registration script needs to see that nothing was published.
    """


@dataclass(frozen=True, slots=True)
class AgentSkill:
    """One entry of an Agent's `skills`, as the registry reports it back."""

    id: str
    name: str
    description: str
    tags: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentInterface:
    """One `Interface`: where an agent or MCP server answers, and how."""

    url: str
    protocol_binding: str


@dataclass(frozen=True, slots=True)
class RegisteredAgent:
    """An `Agent` resource. Every field is output-only in the API."""

    name: str
    agent_id: str
    display_name: str
    description: str
    version: str
    location: str
    uid: str
    create_time: str
    skills: tuple[AgentSkill, ...] = ()
    interfaces: tuple[AgentInterface, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def framework(self) -> str | None:
        """The declared agent framework, when the registry knows one."""
        entry = self.attributes.get("agentregistry.googleapis.com/system/Framework")
        if isinstance(entry, Mapping):
            value = entry.get("framework")
            return str(value) if value else None
        return None

    @property
    def runtime_identity(self) -> str | None:
        """The principal the registry associates with this agent, if any."""
        entry = self.attributes.get("agentregistry.googleapis.com/system/RuntimeIdentity")
        if isinstance(entry, Mapping):
            value = entry.get("principal")
            return str(value) if value else None
        return None


@dataclass(frozen=True, slots=True)
class RegisteredMcpServer:
    """An `McpServer` resource and the tools it advertises."""

    name: str
    mcp_server_id: str
    display_name: str
    description: str
    tool_names: tuple[str, ...] = ()
    interfaces: tuple[AgentInterface, ...] = ()


@dataclass(frozen=True, slots=True)
class RegisteredService:
    """A `Service` — the writable half of the registry."""

    name: str
    display_name: str
    description: str
    spec_type: str
    registry_resource: str


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    """What one `register_service` call did."""

    service_id: str
    service_name: str
    created: bool
    registry_resource: str


def _default_token_provider() -> Callable[[], str]:
    """Mint access tokens from the ambient credentials.

    Resolved through `google.auth.default`, so the same code path works from a
    developer's key file, a Cloud Run runtime identity, and a CI workload
    identity federation without naming any of them.
    """

    def provider() -> str:
        try:
            import google.auth
            import google.auth.transport.requests
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise RegistryUnavailableError("google-auth is not installed") from exc
        try:
            credentials, _ = google.auth.default(scopes=list(REGISTRY_SCOPES))
            credentials.refresh(google.auth.transport.requests.Request())
        except Exception as exc:  # google-auth raises a wide, undocumented family
            raise RegistryUnavailableError(f"could not mint a Google access token: {exc}") from exc
        token = str(credentials.token or "")
        if not token:
            raise RegistryUnavailableError("Google returned an empty access token")
        return token

    return provider


def _urllib_transport(timeout_seconds: float) -> Transport:
    def transport(
        method: str, url: str, body: bytes | None, headers: Mapping[str, str]
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as exc:
            # The body of a Google API error carries `error.message`, which is
            # the only useful part; losing it turns a schema violation into a
            # bare "400".
            return int(exc.code), exc.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise RegistryUnavailableError(
                f"agentregistry.googleapis.com unreachable: {exc}"
            ) from exc

    return transport


def _error_detail(status: int, payload: bytes) -> str:
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return f"HTTP {status}"
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        code = str(error.get("status") or "").strip()
        return f"HTTP {status} {code}: {message}".strip()
    return f"HTTP {status}"


def _skills(raw: Any) -> tuple[AgentSkill, ...]:
    if not isinstance(raw, list):
        return ()
    skills: list[AgentSkill] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        skills.append(
            AgentSkill(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
                tags=tuple(str(tag) for tag in item.get("tags") or ()),
                examples=tuple(str(example) for example in item.get("examples") or ()),
            )
        )
    return tuple(skills)


def _interfaces(raw: Any) -> tuple[AgentInterface, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        AgentInterface(
            url=str(item.get("url") or ""),
            protocol_binding=str(item.get("protocolBinding") or ""),
        )
        for item in raw
        if isinstance(item, dict)
    )


def _agent_interfaces(protocols: Any) -> tuple[AgentInterface, ...]:
    if not isinstance(protocols, list):
        return ()
    found: list[AgentInterface] = []
    for protocol in protocols:
        if isinstance(protocol, dict):
            found.extend(_interfaces(protocol.get("interfaces")))
    return tuple(found)


def _parse_agent(raw: Mapping[str, Any]) -> RegisteredAgent:
    attributes = raw.get("attributes")
    return RegisteredAgent(
        name=str(raw.get("name") or ""),
        agent_id=str(raw.get("agentId") or ""),
        display_name=str(raw.get("displayName") or ""),
        description=str(raw.get("description") or ""),
        version=str(raw.get("version") or ""),
        location=str(raw.get("location") or ""),
        uid=str(raw.get("uid") or ""),
        create_time=str(raw.get("createTime") or ""),
        skills=_skills(raw.get("skills")),
        interfaces=_agent_interfaces(raw.get("protocols")),
        attributes=dict(attributes) if isinstance(attributes, Mapping) else {},
    )


def _parse_mcp_server(raw: Mapping[str, Any]) -> RegisteredMcpServer:
    tools = raw.get("tools")
    names: tuple[str, ...] = ()
    if isinstance(tools, list):
        names = tuple(str(t.get("name") or "") for t in tools if isinstance(t, dict))
    return RegisteredMcpServer(
        name=str(raw.get("name") or ""),
        mcp_server_id=str(raw.get("mcpServerId") or ""),
        display_name=str(raw.get("displayName") or ""),
        description=str(raw.get("description") or ""),
        tool_names=names,
        interfaces=_interfaces(raw.get("interfaces")),
    )


def _spec_type(raw: Mapping[str, Any]) -> str:
    for key in ("agentSpec", "mcpServerSpec", "endpointSpec"):
        spec = raw.get(key)
        if isinstance(spec, Mapping):
            return f"{key}:{spec.get('type') or ''}"
    return ""


def _parse_service(raw: Mapping[str, Any]) -> RegisteredService:
    return RegisteredService(
        name=str(raw.get("name") or ""),
        display_name=str(raw.get("displayName") or ""),
        description=str(raw.get("description") or ""),
        spec_type=_spec_type(raw),
        registry_resource=str(raw.get("registryResource") or ""),
    )


class AgentRegistryClient:
    """Read and publish PatchAPI's entries in one project's agent catalog."""

    def __init__(
        self,
        config: RegistryConfig | None = None,
        *,
        transport: Transport | None = None,
        token_provider: Callable[[], str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config or load_config()
        self._transport = transport or _urllib_transport(self.config.timeout_seconds)
        self._token_provider = token_provider or _default_token_provider()
        self._sleep = sleep

    # -- transport ---------------------------------------------------------

    def _call(
        self,
        method: str,
        url: str,
        *,
        body: Mapping[str, Any] | None = None,
        allow_statuses: Sequence[int] = (),
    ) -> tuple[int, dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self._token_provider()}",
            "Accept": _JSON,
        }
        payload: bytes | None = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = _JSON
        status, raw = self._transport(method, url, payload, headers)
        if status >= 400 and status not in allow_statuses:
            raise RegistryError(f"{method} {url} failed: {_error_detail(status, raw)}")
        if not raw:
            return status, {}
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RegistryError(f"{method} {url} returned a non-JSON body") from exc
        return status, decoded if isinstance(decoded, dict) else {}

    def _require_configured(self) -> None:
        if not self.config.enabled:
            raise RegistryUnavailableError(
                "Agent Registry is disabled for this process; unset PATCHAPI_REGISTRY_ENABLED=0"
            )
        self.config.require_project()

    def _paged(self, collection: str, key: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        url = f"{self.config.collection_url(collection)}?pageSize={PAGE_SIZE}"
        while True:
            _, body = self._call("GET", url)
            items.extend(entry for entry in body.get(key) or () if isinstance(entry, dict))
            token = str(body.get("nextPageToken") or "")
            if not token:
                return items
            url = f"{self.config.collection_url(collection)}?pageSize={PAGE_SIZE}&pageToken={token}"

    # -- reads (fail-soft) -------------------------------------------------

    def _degrade(self, what: str, exc: Exception) -> None:
        log.warning("agent registry %s unavailable: %s", what, exc)

    def list_agents(self) -> tuple[RegisteredAgent, ...]:
        """Every agent this project's catalog knows, PatchAPI's and Google's."""
        try:
            self._require_configured()
            return tuple(_parse_agent(raw) for raw in self._paged("agents", "agents"))
        except (RegistryError, ValueError) as exc:
            self._degrade("agents.list", exc)
            return ()

    def get_agent(self, name: str) -> RegisteredAgent | None:
        """One agent by resource name, or `None` when it cannot be read.

        `None` means "not found *or* not reachable". Callers must not read it as
        "this agent is not registered".
        """
        try:
            self._require_configured()
            _, body = self._call("GET", self.config.resource_url(name))
            return _parse_agent(body)
        except (RegistryError, ValueError) as exc:
            self._degrade(f"agents.get {name}", exc)
            return None

    def search_agents(
        self, query: str, *, page_size: int | None = None
    ) -> tuple[RegisteredAgent, ...]:
        """Keyword and field search over the catalog (`agents:search`)."""
        try:
            self._require_configured()
            body: dict[str, Any] = {"searchString": query}
            if page_size is not None:
                body["pageSize"] = page_size
            _, response = self._call(
                "POST", f"{self.config.collection_url('agents')}:search", body=body
            )
            return tuple(
                _parse_agent(raw) for raw in response.get("agents") or () if isinstance(raw, dict)
            )
        except (RegistryError, ValueError) as exc:
            self._degrade("agents.search", exc)
            return ()

    def list_mcp_servers(self) -> tuple[RegisteredMcpServer, ...]:
        """Every MCP server in this project's catalog."""
        try:
            self._require_configured()
            return tuple(_parse_mcp_server(raw) for raw in self._paged("mcpServers", "mcpServers"))
        except (RegistryError, ValueError) as exc:
            self._degrade("mcpServers.list", exc)
            return ()

    def list_services(self) -> tuple[RegisteredService, ...]:
        """The Service resources this project has published."""
        try:
            self._require_configured()
            return tuple(_parse_service(raw) for raw in self._paged("services", "services"))
        except (RegistryError, ValueError) as exc:
            self._degrade("services.list", exc)
            return ()

    def list_bindings(self) -> tuple[Mapping[str, Any], ...]:
        """Registry bindings, which attach a Service to an Agent Identity provider.

        Returned raw: PatchAPI creates none yet, so there is no shape here worth
        pinning a dataclass to until an `authProviders` resource exists to bind.
        """
        try:
            self._require_configured()
            return tuple(self._paged("bindings", "bindings"))
        except (RegistryError, ValueError) as exc:
            self._degrade("bindings.list", exc)
            return ()

    # -- operations --------------------------------------------------------

    def await_operation(self, operation: Mapping[str, Any]) -> dict[str, Any]:
        """Poll a long-running operation until it is done, then return it.

        The registry answers `services.create` before the Agent resource
        exists, and a schema violation in the spec surfaces here rather than on
        the create call — so an unchecked operation reads as a success that
        published nothing.
        """
        if operation.get("done"):
            return _checked_operation(operation)
        name = str(operation.get("name") or "")
        if not name:
            raise RegistryError("registry returned an operation with no name")
        url = self.config.resource_url(name)
        deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
        while True:
            _, body = self._call("GET", url)
            if body.get("done"):
                return _checked_operation(body)
            if time.monotonic() >= deadline:
                raise RegistryError(
                    f"operation {name} did not finish within {OPERATION_TIMEOUT_SECONDS:.0f}s"
                )
            self._sleep(OPERATION_POLL_INTERVAL_SECONDS)

    # -- writes (explicit) -------------------------------------------------

    def register_service(
        self, *, service_id: str, service: Mapping[str, Any]
    ) -> RegistrationResult:
        """Create or reconcile one Service, then wait for it to take effect.

        Idempotent by design: a second run patches the existing Service rather
        than failing, so re-registering after a prompt-version bump is the same
        command as the first registration.
        """
        self._require_configured()
        body = dict(service)
        body.pop("name", None)
        status, response = self._call(
            "POST",
            f"{self.config.collection_url('services')}?serviceId={service_id}",
            body=body,
            allow_statuses=(409,),
        )
        created = status != 409
        if created:
            self.await_operation(response)
        else:
            mask = ",".join(sorted(body))
            _, patched = self._call(
                "PATCH",
                f"{self.config.collection_url('services')}/{service_id}?updateMask={mask}",
                body=body,
            )
            self.await_operation(patched)

        name = f"{self.config.parent}/services/{service_id}"
        _, current = self._call("GET", self.config.resource_url(name))
        return RegistrationResult(
            service_id=service_id,
            service_name=name,
            created=created,
            registry_resource=str(current.get("registryResource") or ""),
        )

    def register_agent_card(
        self,
        *,
        service_id: str,
        card: Mapping[str, Any],
        display_name: str,
        description: str,
    ) -> RegistrationResult:
        """Publish an A2A agent card as a Service of type Agent.

        `interfaces` is deliberately absent. An `A2A_AGENT_CARD` spec must carry
        its connectivity in the card's own `url` and `preferredTransport`; the
        API rejects a Service that sets both.
        """
        return self.register_service(
            service_id=service_id,
            service={
                "displayName": display_name,
                "description": description,
                "agentSpec": {"type": SPEC_A2A_AGENT_CARD, "content": dict(card)},
            },
        )

    def register_mcp_server(
        self,
        *,
        service_id: str,
        url: str,
        tools: Sequence[Mapping[str, Any]],
        display_name: str,
        description: str,
    ) -> RegistrationResult:
        """Publish an MCP tool surface as a Service of type MCP Server.

        `url` must serve MCP over JSON-RPC. The create operation rejects any
        other protocol binding, so a REST tool service cannot be registered
        here even though it exposes the same operations.
        """
        return self.register_service(
            service_id=service_id,
            service={
                "displayName": display_name,
                "description": description,
                "mcpServerSpec": {
                    "type": SPEC_MCP_TOOL_SPEC,
                    "content": {"tools": [dict(tool) for tool in tools]},
                },
                "interfaces": [
                    {"url": url, "protocolBinding": PROTOCOL_BINDING_JSONRPC},
                ],
            },
        )


def _checked_operation(operation: Mapping[str, Any]) -> dict[str, Any]:
    error = operation.get("error")
    if isinstance(error, Mapping):
        message = str(error.get("message") or "").strip() or "no message"
        raise RegistryError(f"registry operation failed: {message}")
    return dict(operation)


__all__ = [
    "AgentInterface",
    "AgentRegistryClient",
    "AgentSkill",
    "RegisteredAgent",
    "RegisteredMcpServer",
    "RegisteredService",
    "RegistrationResult",
    "RegistryConfig",
    "RegistryError",
    "RegistryUnavailableError",
    "Transport",
    "load_config",
]
