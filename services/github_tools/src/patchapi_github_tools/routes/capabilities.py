"""The capability surface: one catalog route and one invocation route.

A single choke point is deliberate. Every GitHub operation PatchAPI can perform
passes through `invoke_capability`, in this order:

1. the caller names itself and is recognised,
2. the capability name resolves against the shared allowlist — a forbidden name
   is refused here with a 403 that records what was attempted,
3. the caller's grant set contains that capability,
4. the arguments satisfy the capability's contract,
5. the App credentials exist.

Only then is GitHub contacted. Any earlier failure returns a structured error
and no request leaves the process.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from pydantic import ValidationError

from packages.github import (
    FORBIDDEN_CAPABILITIES,
    Capability,
    ForbiddenCapabilityError,
    UnknownCapabilityError,
    is_write_capability,
    resolve_capability,
)
from patchapi_github_tools.dependencies import (
    optional_github_client,
    optional_run_id,
    require_agent_identity,
    require_github_client,
)
from patchapi_github_tools.errors import (
    AUTOMATION_BOUNDARY,
    capability_not_granted,
    forbidden_capability,
    invalid_arguments,
    repository_state_conflict,
    unknown_capability,
    upstream_error,
)
from patchapi_github_tools.github_rest import ForbiddenEndpointError, GitHubRest, UpstreamError
from patchapi_github_tools.identity import AGENT_GRANTS, granted_capabilities
from patchapi_github_tools.operations import REGISTRY, ConflictError

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
    capability = _resolve(capability_name)
    _authorize(agent, capability)
    # The boundary is checked before the credentials deliberately: an attempt to
    # merge is refused as forbidden whether or not the App happens to be wired.
    client = require_github_client(github)

    operation = REGISTRY[capability]
    try:
        parsed = operation.args_model.model_validate(arguments)
    except ValidationError as exc:
        raise invalid_arguments(capability.value, _problems(exc)) from exc

    try:
        result = await operation.handler(client, parsed)
    except ConflictError as exc:
        raise repository_state_conflict(capability.value, exc.code, exc.detail) from exc
    except ForbiddenEndpointError as exc:
        # Defence in depth: the transport refused a URL shape no handler should
        # ever assemble. Reported as a forbidden capability so the audit trail
        # records an attempted boundary crossing rather than a generic 5xx.
        raise forbidden_capability(capability.value) from exc
    except UpstreamError as exc:
        raise upstream_error(capability.value, exc.status_code, exc.message) from exc

    return {
        "capability": capability.value,
        "agent": agent,
        "run_id": run_id,
        "result": result,
    }


def _resolve(name: str) -> Capability:
    try:
        return resolve_capability(name)
    except ForbiddenCapabilityError as exc:
        raise forbidden_capability(name.strip().lower()) from exc
    except UnknownCapabilityError as exc:
        raise unknown_capability(
            name.strip().lower(), sorted(item.value for item in REGISTRY)
        ) from exc


def _problems(exc: ValidationError) -> list[dict[str, str]]:
    """Project a validation failure to location, message, and type.

    Pydantic's own error entries carry the offending input and the original
    exception object. Neither is forwarded: the input may be patch content, and
    the exception is not JSON.
    """
    return [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors(include_url=False)
    ]


def _authorize(agent: str, capability: Capability) -> None:
    granted = granted_capabilities(agent)
    if capability not in granted:
        raise capability_not_granted(
            agent, capability.value, sorted(item.value for item in granted)
        )
