"""The single path from a capability name to a GitHub call.

Two transports reach GitHub through this service — the versioned REST route and
the MCP JSON-RPC endpoint — and they must not become two security postures. The
gates therefore live in one function rather than once per transport, so a new
transport cannot omit one or reorder them:

1. the capability name resolves against the shared allowlist — a forbidden name
   is refused here, ahead of everything else, so an attempt to merge is recorded
   as an attempted boundary crossing whatever else is true about the caller,
2. the caller's grant set contains that capability,
3. the App credentials exist,
4. the arguments satisfy the capability's contract.

The caller's identity is established before this module is reached: it selects
the grant set, so there is nothing here to check it against if it is absent.

Refusals are raised as `HTTPException` regardless of transport. The REST route
returns them unchanged; the MCP route translates the same structured detail into
a JSON-RPC error object, so both audit trails carry identical content.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from packages.github import (
    Capability,
    ForbiddenCapabilityError,
    UnknownCapabilityError,
    resolve_capability,
)
from patchapi_github_tools.dependencies import require_github_client
from patchapi_github_tools.errors import (
    capability_not_granted,
    forbidden_capability,
    invalid_arguments,
    repository_state_conflict,
    unknown_capability,
    upstream_error,
)
from patchapi_github_tools.github_rest import ForbiddenEndpointError, GitHubRest, UpstreamError
from patchapi_github_tools.identity import granted_capabilities
from patchapi_github_tools.operations import REGISTRY, ConflictError


def resolve_or_refuse(name: str) -> Capability:
    """Return the `Capability` `name` denotes, or raise the matching refusal.

    A forbidden name and an unrecognised name are different events for a security
    reviewer, so they keep different error codes all the way out to the caller.
    """
    try:
        return resolve_capability(name)
    except ForbiddenCapabilityError as exc:
        raise forbidden_capability(name.strip().lower()) from exc
    except UnknownCapabilityError as exc:
        raise unknown_capability(
            name.strip().lower(), sorted(item.value for item in REGISTRY)
        ) from exc


def authorize(agent: str, capability: Capability) -> None:
    """Raise unless `agent` holds `capability`."""
    granted = granted_capabilities(agent)
    if capability not in granted:
        raise capability_not_granted(
            agent, capability.value, sorted(item.value for item in granted)
        )


def validation_problems(exc: ValidationError) -> list[dict[str, str]]:
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


async def execute_capability(
    *,
    capability_name: str,
    agent: str,
    github: GitHubRest | None,
    run_id: str | None,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Run one capability for one agent, or raise a structured refusal."""
    capability = resolve_or_refuse(capability_name)
    authorize(agent, capability)
    # The boundary is checked before the credentials deliberately: an attempt to
    # merge is refused as forbidden whether or not the App happens to be wired.
    client = require_github_client(github)

    operation = REGISTRY[capability]
    try:
        parsed = operation.args_model.model_validate(dict(arguments))
    except ValidationError as exc:
        raise invalid_arguments(capability.value, validation_problems(exc)) from exc

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
