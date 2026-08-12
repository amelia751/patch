"""The GitHub capability vocabulary agents are allowed to name (roadmap §7.3).

Agents receive capabilities, never tokens. This module is the deterministic
half of that boundary: the allowlist is an enum, and the operations PatchAPI
must never perform are listed separately by name so an attempt to reach one is
a distinguishable, auditable refusal rather than an anonymous "unknown tool".

Nothing here performs a request. `services/github_tools` owns the credentials
and the transport; it resolves names through this module first.
"""

from enum import StrEnum
from typing import Final


class Capability(StrEnum):
    """Every operation the GitHub tool service may expose.

    Membership is the allowlist. A capability that is absent cannot be granted,
    which is why the forbidden operations below are not members.
    """

    GET_REPOSITORY_METADATA = "get_repository_metadata"
    GET_FILE = "get_file"
    LIST_TREE = "list_tree"
    GET_COMMIT = "get_commit"
    GET_PULL_REQUEST = "get_pull_request"
    GET_CHECKS = "get_checks"

    CREATE_PATCH_BRANCH = "create_patch_branch"
    COMMIT_VERIFIED_PATCH = "commit_verified_patch"
    OPEN_PULL_REQUEST = "open_pull_request"
    ADD_PR_COMMENT = "add_pr_comment"


READ_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {
        Capability.GET_REPOSITORY_METADATA,
        Capability.GET_FILE,
        Capability.LIST_TREE,
        Capability.GET_COMMIT,
        Capability.GET_PULL_REQUEST,
        Capability.GET_CHECKS,
    }
)

WRITE_CAPABILITIES: Final[frozenset[Capability]] = frozenset(Capability) - READ_CAPABILITIES

# Named, not implemented. PatchAPI stops at the pull request: merging,
# branch-protection changes, secret writes, admin settings, and repository
# deletion stay with the existing enterprise controls. Keeping the names here
# lets a refusal say what was attempted.
FORBIDDEN_CAPABILITIES: Final[frozenset[str]] = frozenset(
    {
        "merge_pull_request",
        "squash_merge_pull_request",
        "rebase_merge_pull_request",
        "change_branch_protection",
        "dismiss_review",
        "approve_pull_request",
        "modify_actions_secrets",
        "modify_repository_admin_settings",
        "add_collaborator",
        "delete_repository",
        "delete_branch_protection_rule",
        "update_codeowners",
    }
)


class CapabilityError(ValueError):
    """Base class for a refused capability name."""


class ForbiddenCapabilityError(CapabilityError):
    """The name is a real GitHub operation PatchAPI must never perform."""


class UnknownCapabilityError(CapabilityError):
    """The name is not part of the exposed surface at all."""


def resolve_capability(name: str) -> Capability:
    """Return the `Capability` for `name`, or fail closed.

    A forbidden name and an unrecognised name both raise; they raise different
    exceptions so the audit log can record "tried to merge" distinctly from
    "asked for something that does not exist".
    """
    normalized = name.strip().lower()
    if normalized in FORBIDDEN_CAPABILITIES:
        raise ForbiddenCapabilityError(
            f"capability {normalized!r} is not exposed by PatchAPI: "
            "the workflow stops at the pull request"
        )
    try:
        return Capability(normalized)
    except ValueError as exc:
        known = ", ".join(sorted(c.value for c in Capability))
        raise UnknownCapabilityError(
            f"unknown GitHub capability {normalized!r}; exposed capabilities: {known}"
        ) from exc


def is_write_capability(capability: Capability) -> bool:
    """True when exercising `capability` changes state in the customer's repo."""
    return capability in WRITE_CAPABILITIES
