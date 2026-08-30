"""Google Agent Registry publication and lookup (roadmap §12.1).

The catalog is how an enterprise discovers which agents exist and what each one
claims it can do. Reads degrade rather than raise, so a registry outage costs
the fleet its listing and never its run.
"""

from packages.platform.config import (
    A2A_INPUT_MODES,
    A2A_OUTPUT_MODES,
    A2A_PROTOCOL_VERSION,
    CATALOG_VERSION,
    DEFAULT_LOCATION,
    ENV_A2A_BASE_URL,
    ENV_ENABLED,
    ENV_LOCATION,
    ENV_MCP_URL,
    ENV_PROJECT,
    MCP_SERVICE_ID,
    SERVICE_ID_PREFIX,
    RegistryConfig,
    load_config,
)
from packages.platform.registry import (
    AgentInterface,
    AgentRegistryClient,
    AgentSkill,
    RegisteredAgent,
    RegisteredMcpServer,
    RegisteredService,
    RegistrationResult,
    RegistryError,
    RegistryUnavailableError,
)

__all__ = [
    "A2A_INPUT_MODES",
    "A2A_OUTPUT_MODES",
    "A2A_PROTOCOL_VERSION",
    "CATALOG_VERSION",
    "DEFAULT_LOCATION",
    "ENV_A2A_BASE_URL",
    "ENV_ENABLED",
    "ENV_LOCATION",
    "ENV_MCP_URL",
    "ENV_PROJECT",
    "MCP_SERVICE_ID",
    "SERVICE_ID_PREFIX",
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
    "load_config",
]
