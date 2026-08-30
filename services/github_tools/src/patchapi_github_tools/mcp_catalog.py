"""MCP tool descriptors, generated from the capability registry.

Published in an agent catalog, these descriptors are how a department that has
never read this repository learns what PatchAPI's GitHub surface can and cannot
do. They are therefore derived, never written by hand: `inputSchema` comes from
the same Pydantic model the REST route validates against, and the read/write
hints come from the shared allowlist. A hand-maintained copy would drift, and a
drifted catalog advertises a boundary the service does not actually enforce.

The forbidden operations need no filtering step: they are not registry members,
so there is no descriptor for them to be omitted from.
"""

from collections.abc import Mapping
from typing import Any, Final

from packages.github import READ_CAPABILITIES, Capability
from patchapi_github_tools.errors import AUTOMATION_BOUNDARY
from patchapi_github_tools.identity import granted_capabilities
from patchapi_github_tools.models import CapabilityArgs
from patchapi_github_tools.operations import REGISTRY

# `idempotentHint` claims a repeat has no *additional* effect, so only the
# operations that actually converge may set it. `create_patch_branch` accepts a
# branch already at the requested base and `open_pull_request` is keyed on
# (run, base SHA, title); `commit_verified_patch` refuses a replay because the
# branch has moved, and `add_pr_comment` would post a second comment.
_IDEMPOTENT: Final[frozenset[Capability]] = READ_CAPABILITIES | {
    Capability.CREATE_PATCH_BRANCH,
    Capability.OPEN_PULL_REQUEST,
}

# The argument models are acyclic — a nested model never references its own
# container — so reference substitution terminates. The limit exists to fail
# loudly if that ever stops being true, rather than to recurse forever.
_MAX_SCHEMA_DEPTH: Final[int] = 32


def input_schema(model: type[CapabilityArgs]) -> dict[str, Any]:
    """Return `model`'s JSON Schema with every internal reference inlined.

    The consumer of a published tool spec is a function-calling schema
    validator, not a full JSON Schema implementation, and those generally reject
    `$ref`. Inlining keeps the schema self-contained without maintaining a second
    description of arguments the REST route already validates.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    return _inline_references(schema, definitions, depth=0)


def tool_descriptor(capability: Capability) -> dict[str, Any]:
    """Describe one capability in MCP's vocabulary."""
    operation = REGISTRY[capability]
    read_only = capability in READ_CAPABILITIES
    return {
        "name": capability.value,
        "description": _description(capability, read_only=read_only),
        "inputSchema": input_schema(operation.args_model),
        "annotations": {
            "title": operation.summary,
            "readOnlyHint": read_only,
            # No exposed operation deletes, force-pushes, or rewrites history:
            # the four writes create a branch, a commit, a pull request, or a
            # comment, and each is confined to PatchAPI's own branch prefix.
            "destructiveHint": False,
            "idempotentHint": capability in _IDEMPOTENT,
            # Every capability reaches GitHub, whose state PatchAPI does not own.
            "openWorldHint": True,
        },
    }


def tools_for_agent(agent: str) -> list[dict[str, Any]]:
    """Describe only the capabilities `agent` holds.

    The catalog view is per identity for the same reason invocation is: an agent
    that cannot exercise an operation should not be told the operation is
    available to it. An unknown or ungranted caller sees an empty list.
    """
    granted = granted_capabilities(agent)
    return [
        tool_descriptor(capability)
        for capability in sorted(REGISTRY, key=lambda item: item.value)
        if capability in granted
    ]


def _description(capability: Capability, *, read_only: bool) -> str:
    kind = "Read-only" if read_only else "Write"
    return (
        f"{REGISTRY[capability].summary}. {kind} GitHub operation exposed by "
        f"PatchAPI. {AUTOMATION_BOUNDARY}"
    )


def _inline_references(node: Any, definitions: Mapping[str, Any], *, depth: int) -> Any:
    if depth > _MAX_SCHEMA_DEPTH:
        raise ValueError("argument schema nests deeper than the inlining limit allows")

    if isinstance(node, list):
        return [_inline_references(item, definitions, depth=depth + 1) for item in node]
    if not isinstance(node, dict):
        return node

    reference = node.get("$ref")
    if isinstance(reference, str):
        name = reference.removeprefix("#/$defs/")
        if name not in definitions:
            raise ValueError(f"argument schema references an unknown definition: {reference!r}")
        # Sibling keys survive the substitution: Pydantic emits a `$ref`
        # alongside a description or default, and dropping those would publish a
        # weaker contract than the one the REST route enforces.
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        resolved = _inline_references(definitions[name], definitions, depth=depth + 1)
        return {**resolved, **_inline_references(siblings, definitions, depth=depth + 1)}

    return {
        key: _inline_references(value, definitions, depth=depth + 1) for key, value in node.items()
    }
