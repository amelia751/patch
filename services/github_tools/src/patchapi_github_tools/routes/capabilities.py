"""The capability surface: one catalog route and one invocation route.

A single choke point is deliberate. Every GitHub operation PatchAPI can perform
passes through `patchapi_github_tools.invocation.execute_capability`, which owns
the ordered gates; this module only supplies the HTTP shape around them. The MCP
endpoint calls the same function, so neither transport can drift into a wider
posture than the other.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from packages.github import FORBIDDEN_CAPABILITIES, is_write_capability
from patchapi_github_tools.dependencies import (
    optional_github_client,
    optional_run_id,
    require_agent_identity,
)
from patchapi_github_tools.errors import AUTOMATION_BOUNDARY
from patchapi_github_tools.github_rest import GitHubRest
from patchapi_github_tools.identity import AGENT_GRANTS
from patchapi_github_tools.invocation import execute_capability
from patchapi_github_tools.operations import REGISTRY

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities", summary="List the exposed capability surface")
async def list_capabilities() -> dict[str, Any]:
    """Describe what may be asked for, by whom, and what is never exposed."""
    return {
        "exposed": [
            {
                "name": capability.value,
                "kind": "write" if is_write_capability(capability) else "read",
                "summary": REGISTRY[capability].summary,
            }
            for capability in sorted(REGISTRY, key=lambda item: item.value)
        ],
        "never_exposed": sorted(FORBIDDEN_CAPABILITIES),
        "automation_boundary": AUTOMATION_BOUNDARY,
        "grants": {
            agent: sorted(capability.value for capability in capabilities)
            for agent, capabilities in sorted(AGENT_GRANTS.items())
        },
    }


@router.post("/capabilities/{capability_name}", summary="Invoke one capability")
async def invoke_capability(
    capability_name: str,
    agent: Annotated[str, Depends(require_agent_identity)],
    github: Annotated[GitHubRest | None, Depends(optional_github_client)],
    run_id: Annotated[str | None, Depends(optional_run_id)],
    arguments: Annotated[dict[str, Any], Body(default_factory=dict)],
) -> dict[str, Any]:
    return await execute_capability(
        capability_name=capability_name,
        agent=agent,
        github=github,
        run_id=run_id,
        arguments=arguments,
    )
