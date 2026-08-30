"""MCP JSON-RPC 2.0 over HTTP for the capability surface.

The point of this endpoint is discovery without new privilege. A catalog entry
lets another department find PatchAPI's GitHub surface and read, in MCP's own
vocabulary, that it is mostly read-only, that its four write operations are
non-destructive, and that merge, administration, secret, and branch-protection
operations are absent entirely. Nothing here widens anything: `tools/call` goes
through `execute_capability`, the same gates in the same order as the REST route,
and `tools/list` shows only what the calling identity holds.

Two boundaries are drawn deliberately.

*Authentication stays at the transport.* An unrecognised caller is refused with
401 before any envelope is parsed, exactly as on the REST route: the identity
selects the grant set, so there is no anonymous JSON-RPC conversation to have.

*Everything after that is JSON-RPC.* A malformed envelope, an unknown method, and
a refused capability all return HTTP 200 with an error object, because a client
that cannot frame a request has a different problem from one whose request was
refused, and an HTTP status cannot tell the two apart. The refusal codes below
preserve the REST distinctions — "tried to merge" stays separate from "not
granted" and from "misspelled a name" — and each error carries the REST refusal
detail verbatim in `data`, so both transports leave the same audit record.
"""

import json
from collections.abc import Mapping
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from patchapi_github_tools.config import (
    MCP_ACCEPTED_PROTOCOL_VERSIONS,
    MCP_PATH,
    MCP_PROTOCOL_VERSION,
    SERVICE_NAME,
    SERVICE_VERSION,
)
from patchapi_github_tools.dependencies import (
    optional_github_client,
    optional_run_id,
    require_agent_identity,
)
from patchapi_github_tools.errors import (
    AUTOMATION_BOUNDARY,
    CAPABILITY_NOT_GRANTED,
    DEPENDENCY_UNAVAILABLE,
    FORBIDDEN_CAPABILITY,
    INVALID_ARGUMENTS,
    REPOSITORY_STATE_CONFLICT,
    UNKNOWN_CAPABILITY,
    UPSTREAM_ERROR,
)
from patchapi_github_tools.github_rest import GitHubRest
from patchapi_github_tools.invocation import execute_capability
from patchapi_github_tools.mcp_catalog import tools_for_agent

JSONRPC_VERSION: Final[str] = "2.0"

PARSE_ERROR: Final[int] = -32700
INVALID_REQUEST: Final[int] = -32600
METHOD_NOT_FOUND: Final[int] = -32601
INVALID_PARAMS: Final[int] = -32602
INTERNAL_ERROR: Final[int] = -32603

# JSON-RPC reserves -32000..-32099 for implementation-defined server errors.
# Each refusal keeps its own code so a catalog client and an audit reader can
# distinguish the boundary crossings from the ordinary failures.
CAPABILITY_FORBIDDEN_CODE: Final[int] = -32001
CAPABILITY_NOT_GRANTED_CODE: Final[int] = -32002
DEPENDENCY_UNAVAILABLE_CODE: Final[int] = -32003
REPOSITORY_STATE_CONFLICT_CODE: Final[int] = -32004
UPSTREAM_ERROR_CODE: Final[int] = -32005

_REFUSAL_CODES: Final[Mapping[str, int]] = {
    FORBIDDEN_CAPABILITY: CAPABILITY_FORBIDDEN_CODE,
    CAPABILITY_NOT_GRANTED: CAPABILITY_NOT_GRANTED_CODE,
    DEPENDENCY_UNAVAILABLE: DEPENDENCY_UNAVAILABLE_CODE,
    REPOSITORY_STATE_CONFLICT: REPOSITORY_STATE_CONFLICT_CODE,
    UPSTREAM_ERROR: UPSTREAM_ERROR_CODE,
    # An unexposed name and unsatisfied arguments are both "the parameters you
    # sent cannot be honoured", which is what JSON-RPC's invalid-params means.
    # The `error` field in `data` still separates them.
    UNKNOWN_CAPABILITY: INVALID_PARAMS,
    INVALID_ARGUMENTS: INVALID_PARAMS,
}

_REFUSAL_MESSAGES: Final[Mapping[str, str]] = {
    FORBIDDEN_CAPABILITY: "that operation is not part of this surface",
    CAPABILITY_NOT_GRANTED: "the calling agent does not hold that capability",
    UNKNOWN_CAPABILITY: "unknown tool",
    INVALID_ARGUMENTS: "the arguments do not satisfy the tool's contract",
    DEPENDENCY_UNAVAILABLE: "a required dependency is not configured; no call was attempted",
    REPOSITORY_STATE_CONFLICT: "the repository is not in the state the caller verified against",
    UPSTREAM_ERROR: "GitHub refused or failed the call",
}

_INSTRUCTIONS: Final[str] = (
    "PatchAPI's narrow GitHub capability adapter. This server holds the GitHub "
    "App credentials and never returns one: callers name a capability and "
    "receive a result. `tools/list` reflects only what the identity in the "
    f"request headers is granted. {AUTOMATION_BOUNDARY}"
)

router = APIRouter(tags=["mcp"])


@router.post(
    MCP_PATH,
    summary="MCP JSON-RPC endpoint for the capability surface",
    response_model=None,
)
async def mcp_jsonrpc(
    request: Request,
    agent: Annotated[str, Depends(require_agent_identity)],
    github: Annotated[GitHubRest | None, Depends(optional_github_client)],
    run_id: Annotated[str | None, Depends(optional_run_id)],
) -> Response:
    raw = await request.body()
    try:
        envelope = json.loads(raw) if raw else None
    except ValueError:
        return _failure(None, PARSE_ERROR, "request body is not valid JSON")

    if isinstance(envelope, list):
        # Removed from MCP as of the 2025-06-18 revision. Refusing is honest;
        # accepting would mean maintaining an ordering guarantee no client needs.
        return _failure(None, INVALID_REQUEST, "JSON-RPC batches are not supported")
    if not isinstance(envelope, dict):
        return _failure(None, INVALID_REQUEST, "a JSON-RPC request must be a JSON object")

    # The id is read before anything else is judged so that a rejection can be
    # correlated by the client. JSON-RPC only permits a null id in a response
    # when the id could not be determined at all.
    request_id = envelope.get("id")
    if request_id is not None and not _is_valid_id(request_id):
        return _failure(None, INVALID_REQUEST, "'id' must be a string, a number, or absent")

    if envelope.get("jsonrpc") != JSONRPC_VERSION:
        return _failure(request_id, INVALID_REQUEST, f"'jsonrpc' must be {JSONRPC_VERSION!r}")

    method = envelope.get("method")
    if not isinstance(method, str) or not method.strip():
        return _failure(request_id, INVALID_REQUEST, "'method' must be a non-empty string")

    # A notification carries no id, and JSON-RPC forbids answering one — an
    # unhandled notification is accepted silently rather than turned into an
    # error the client has nowhere to put.
    if request_id is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)

    params = envelope.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _failure(request_id, INVALID_PARAMS, "'params' must be an object")

    if method == "initialize":
        return _success(request_id, _initialize(params))
    if method == "ping":
        return _success(request_id, {})
    if method == "tools/list":
        return _success(request_id, {"tools": tools_for_agent(agent)})
    if method == "tools/call":
        return await _call_tool(request_id, params, agent=agent, github=github, run_id=run_id)

    return _failure(request_id, METHOD_NOT_FOUND, f"unsupported method {method!r}")


def _is_valid_id(value: Any) -> bool:
    # `bool` is a subclass of `int`, and `true` is not a JSON-RPC id.
    return isinstance(value, str | int | float) and not isinstance(value, bool)


def _initialize(params: Mapping[str, Any]) -> dict[str, Any]:
    requested = params.get("protocolVersion")
    version = (
        requested
        if isinstance(requested, str) and requested in MCP_ACCEPTED_PROTOCOL_VERSIONS
        else MCP_PROTOCOL_VERSION
    )
    return {
        "protocolVersion": version,
        # No prompts, no resources, no sampling: the only thing this server does
        # is expose the capability allowlist as tools.
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVICE_NAME, "version": SERVICE_VERSION},
        "instructions": _INSTRUCTIONS,
    }


async def _call_tool(
    request_id: Any,
    params: Mapping[str, Any],
    *,
    agent: str,
    github: GitHubRest | None,
    run_id: str | None,
) -> Response:
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        return _failure(request_id, INVALID_PARAMS, "'name' must be a non-empty string")

    arguments = params.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _failure(request_id, INVALID_PARAMS, "'arguments' must be an object")

    try:
        result = await execute_capability(
            capability_name=name,
            agent=agent,
            github=github,
            run_id=run_id,
            arguments=arguments,
        )
    except HTTPException as exc:
        return _refusal(request_id, exc)

    # The structured envelope is the contract; the text block is the same data
    # rendered for a client that only reads `content`. They are not allowed to
    # diverge, so one is serialised from the other.
    return _success(
        request_id,
        {
            "content": [{"type": "text", "text": json.dumps(result, indent=2, sort_keys=True)}],
            "structuredContent": result,
            "isError": False,
        },
    )


def _refusal(request_id: Any, exc: HTTPException) -> Response:
    """Translate a REST refusal into a JSON-RPC error without losing detail."""
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": "refused"}
    code_name = str(detail.get("error", ""))
    return _failure(
        request_id,
        _REFUSAL_CODES.get(code_name, INTERNAL_ERROR),
        _REFUSAL_MESSAGES.get(code_name, "the request was refused"),
        data={**detail, "http_status": exc.status_code},
    )


def _success(request_id: Any, result: Mapping[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": dict(result)},
    )


def _failure(
    request_id: Any, code: int, message: str, *, data: Mapping[str, Any] | None = None
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = dict(data)
    # 200 even for an error object: the transport succeeded, and the JSON-RPC
    # layer is where the failure is described.
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error},
    )
