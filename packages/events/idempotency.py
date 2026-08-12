"""Idempotency keys for external actions (roadmap §9).

Every action with a side effect outside PatchAPI — opening a PR, allocating a
sandbox, writing an artifact — is keyed by `run_id + action_type + base_sha`.
A resumed process checks persistent state for the key before repeating the
action, which is what keeps a retry from opening a second pull request.

The key is deterministic and carries no clock: two processes computing it for
the same action must agree, so nothing here may vary between calls.
"""

import hashlib
import re
from enum import StrEnum
from typing import Final

_SHA_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ActionType(StrEnum):
    """External actions that must happen at most once per run and base SHA."""

    ALLOCATE_SANDBOX = "allocate_sandbox"
    WRITE_ARTIFACT = "write_artifact"
    CREATE_PATCH_BRANCH = "create_patch_branch"
    COMMIT_PATCH = "commit_patch"
    OPEN_PULL_REQUEST = "open_pull_request"
    ADD_PR_COMMENT = "add_pr_comment"
    PUBLISH_EVENT = "publish_event"


def idempotency_key(run_id: str, action_type: ActionType | str, base_sha: str) -> str:
    """Return the canonical key for one external action.

    Readable rather than hashed: this string is stored in Postgres and read by
    a human debugging a stuck run. Use `key_digest` where a fixed-width column
    or a header value is needed.
    """
    if not _RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run id: {run_id!r}")
    action = ActionType(action_type) if not isinstance(action_type, ActionType) else action_type
    if not _SHA_RE.match(base_sha):
        raise ValueError(
            f"idempotency keys pin a full lowercase 40-character base SHA, got {base_sha!r}"
        )
    return f"{run_id}:{action.value}:{base_sha}"


def key_digest(key: str) -> str:
    """A stable 64-character digest of an idempotency key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
