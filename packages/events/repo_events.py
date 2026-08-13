"""Envelopes for the repository lifecycle the indexer subscribes to.

`repo-indexer.md` §6 names four of them — repo push, repository added to a
project, repository removed, index updated — and requires every one to carry
`repository` **and** `branch`. Branch is not decoration: findings are facts
about a `(repository, branch, commit)`, and an event that omitted the branch
would make a subscriber guess which shard to touch.

The builders live here rather than at each call site so that the payload keys
and the deterministic ids are defined once. Ids are derived from the facts of
the event, never from a clock or a counter: GitHub redelivers, Pub/Sub delivers
at least once, and a replayed push must reduce to the same `run_id` and the same
`idempotency_key` so a subscriber can recognise it as work it has already done.

`occurred_at` is passed in by the caller. Everything else about an envelope is a
pure function of its inputs, and the clock is the one thing that cannot be.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final

from packages.events.config import EventType, TrustLevel
from packages.events.envelope import EventEnvelope

# A push is GitHub reporting a fact about the enterprise's own repository. It is
# not provider material, so it is not labelled untrusted — but the *contents* of
# the repository never travel in the payload either way (roadmap §10.4).
_REPO_TRUST: Final[TrustLevel] = TrustLevel.INTERNAL_ANALYSIS

_UNSAFE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")

BRANCH_REF_PREFIX: Final[str] = "refs/heads/"


def branch_from_ref(ref: str) -> str | None:
    """Return the branch a `refs/heads/...` ref names, or `None` for anything else.

    A tag or a note push is not a branch, and there is no branch to attribute
    findings to. The caller acknowledges it and indexes nothing.
    """
    if not ref.startswith(BRANCH_REF_PREFIX):
        return None
    return ref[len(BRANCH_REF_PREFIX) :] or None


def _slug(value: str) -> str:
    """Reduce a repository or branch to the run-id alphabet (`idempotency.py`)."""
    cleaned = _UNSAFE.sub("-", value).strip("-")
    return cleaned or "unnamed"


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def repo_push_event(
    *,
    repository: str,
    branch: str,
    before_sha: str,
    after_sha: str,
    installation_id: int | None,
    occurred_at: str,
    delivery_id: str | None = None,
) -> EventEnvelope:
    """The `repo-push` envelope a webhook receiver enqueues.

    Scalars only, and no file list: a monorepo push touching ten thousand paths
    is the same size on the wire as one touching a single file. The subscriber
    computes the diff itself, from the two SHAs.

    `delivery_id` names the GitHub delivery when one is known, which keeps two
    distinct deliveries of the same push distinguishable in a log while the
    idempotency key still collapses them into one unit of work.
    """
    key = f"repo-push:{repository}:{branch}:{after_sha}"
    return EventEnvelope(
        event_type=EventType.REPO_PUSH,
        event_id=delivery_id or _digest("repo-push", repository, branch, after_sha),
        run_id=f"push-{_slug(repository)}-{_slug(branch)}-{after_sha[:12]}",
        occurred_at=occurred_at,
        trust=_REPO_TRUST,
        payload={
            "repository": repository,
            "branch": branch,
            "before_sha": before_sha,
            "after_sha": after_sha,
            "installation_id": installation_id,
        },
    ).with_idempotency_key(key)


def project_repo_added_event(
    *,
    project_id: str,
    repository: str,
    branch: str,
    occurred_at: str,
) -> EventEnvelope:
    """The `project-repo-added` envelope the console publishes after the row lands.

    Published per `(project, repository, branch)` because that is the unit the
    indexer references a shard for: two projects importing the same repository
    are two events, one shard, and one set of findings.
    """
    key = f"project-repo-added:{project_id}:{repository}:{branch}"
    return EventEnvelope(
        event_type=EventType.PROJECT_REPO_ADDED,
        event_id=_digest("project-repo-added", project_id, repository, branch),
        run_id=f"import-{_slug(repository)}-{_slug(branch)}",
        occurred_at=occurred_at,
        trust=_REPO_TRUST,
        payload={
            "project_id": project_id,
            "repository": repository,
            "branch": branch,
        },
    ).with_idempotency_key(key)


def project_repo_removed_event(
    *,
    project_id: str,
    repository: str,
    branch: str,
    occurred_at: str,
) -> EventEnvelope:
    """The `project-repo-removed` envelope: one project's reference is released.

    The shard itself survives until the last project releases it, so this event
    is a decrement and not a delete instruction.
    """
    key = f"project-repo-removed:{project_id}:{repository}:{branch}"
    return EventEnvelope(
        event_type=EventType.PROJECT_REPO_REMOVED,
        event_id=_digest("project-repo-removed", project_id, repository, branch),
        run_id=f"release-{_slug(repository)}-{_slug(branch)}",
        occurred_at=occurred_at,
        trust=_REPO_TRUST,
        payload={
            "project_id": project_id,
            "repository": repository,
            "branch": branch,
        },
    ).with_idempotency_key(key)


def index_updated_event(
    *,
    repository: str,
    branch: str,
    indexed_sha: str,
    project_id: str | None = None,
    occurred_at: str,
) -> EventEnvelope:
    """The `index-updated` envelope fanned out to each project after a pass.

    `project_id` is the fan-out target from `projects_for`; `None` addresses the
    repository itself, for a pass that ran before any project claimed it.
    """
    scope = project_id or "-"
    key = f"index-updated:{scope}:{repository}:{branch}:{indexed_sha}"
    return EventEnvelope(
        event_type=EventType.INDEX_UPDATED,
        event_id=_digest("index-updated", scope, repository, branch, indexed_sha),
        run_id=f"index-{_slug(repository)}-{_slug(branch)}-{indexed_sha[:12]}",
        occurred_at=occurred_at,
        trust=_REPO_TRUST,
        payload={
            "project_id": project_id,
            "repository": repository,
            "branch": branch,
            "indexed_sha": indexed_sha,
        },
    ).with_idempotency_key(key)


__all__ = [
    "BRANCH_REF_PREFIX",
    "branch_from_ref",
    "index_updated_event",
    "project_repo_added_event",
    "project_repo_removed_event",
    "repo_push_event",
]
