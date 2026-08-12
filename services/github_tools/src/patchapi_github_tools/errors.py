"""Structured refusals.

Every failure carries a machine-readable `error` code because the audit trail
has to distinguish "an agent tried to merge a pull request" from "an agent
misspelled a tool name" from "the App is not configured". Collapsing those into
one anonymous 4xx would hide the only event a security reviewer cares about.

Refusal messages name the capability that was attempted. They never name a
credential, a token, or a private key.
"""

from typing import Any, Final

from fastapi import HTTPException, status

FORBIDDEN_CAPABILITY: Final[str] = "forbidden_capability"
UNKNOWN_CAPABILITY: Final[str] = "unknown_capability"
UNKNOWN_AGENT: Final[str] = "unknown_agent"
CAPABILITY_NOT_GRANTED: Final[str] = "capability_not_granted"
INVALID_ARGUMENTS: Final[str] = "invalid_arguments"
DEPENDENCY_UNAVAILABLE: Final[str] = "dependency_unavailable"
UPSTREAM_ERROR: Final[str] = "upstream_error"
REPOSITORY_STATE_CONFLICT: Final[str] = "repository_state_conflict"

# Named in every forbidden-capability refusal so the reason survives into the
# caller's own logs, not just ours.
AUTOMATION_BOUNDARY: Final[str] = (
    "PatchAPI stops at the pull request. Merge, administration, secret, and "
    "branch-protection operations are not part of this service and cannot be granted."
)


def forbidden_capability(name: str) -> HTTPException:
    """403 for a real GitHub operation PatchAPI must never perform."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": FORBIDDEN_CAPABILITY,
            "capability": name,
            "reason": AUTOMATION_BOUNDARY,
        },
    )


def unknown_capability(name: str, exposed: list[str]) -> HTTPException:
    """404 for a name that is not part of the exposed surface at all."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": UNKNOWN_CAPABILITY,
            "capability": name,
            "exposed_capabilities": exposed,
        },
    )


def unknown_agent(agent: str, header: str) -> HTTPException:
    """401 when the caller does not present a recognised agent identity."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": UNKNOWN_AGENT, "agent": agent, "identity_header": header},
    )


def capability_not_granted(agent: str, capability: str, granted: list[str]) -> HTTPException:
    """403 when the capability exists but this agent may not exercise it.

    Least privilege is per agent, not per service: the Change Intelligence Agent
    reads untrusted provider material and therefore holds no repository grants
    at all (roadmap §8.1).
    """
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": CAPABILITY_NOT_GRANTED,
            "agent": agent,
            "capability": capability,
            "granted_capabilities": granted,
        },
    )


def invalid_arguments(capability: str, problems: Any) -> HTTPException:
    """422 when the arguments do not satisfy the capability's contract."""
    # 422 by number: Starlette renamed its constant for this code, and pinning
    # the literal keeps the contract stable across that rename.
    return HTTPException(
        status_code=422,
        detail={"error": INVALID_ARGUMENTS, "capability": capability, "problems": problems},
    )


def dependency_unavailable(dependency: str, reason: str) -> HTTPException:
    """503 for a dependency the service needs but does not have.

    Fail closed: without App credentials the caller is told the request was not
    performed, never that it succeeded.
    """
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"error": DEPENDENCY_UNAVAILABLE, "dependency": dependency, "reason": reason},
    )


def upstream_error(capability: str, upstream_status: int, message: str) -> HTTPException:
    """502 when GitHub refused or failed the call.

    The upstream body is not forwarded verbatim; only a status and a short
    message cross the boundary, so a response that happens to echo a header
    cannot leak one.
    """
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "error": UPSTREAM_ERROR,
            "capability": capability,
            "upstream_status": upstream_status,
            "message": message,
        },
    )


def repository_state_conflict(capability: str, code: str, detail: dict[str, Any]) -> HTTPException:
    """409 when the repository is not in the state the caller verified against.

    A patch verified against one commit must not be committed onto another, so
    a moved branch is reported rather than reconciled.
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": REPOSITORY_STATE_CONFLICT,
            "capability": capability,
            "conflict": code,
            **detail,
        },
    )


class CredentialsUnavailableError(RuntimeError):
    """The GitHub App credentials are absent or unusable.

    Raised while loading configuration, before any request is attempted. The
    message names the missing environment variable, never a value.
    """
