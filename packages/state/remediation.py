"""Writing what a remediation run did, as it does it.

The orchestrator already knows how to migrate a repository. What it could not do
was survive its own process: every stage result lived in `RunContext`, in
memory, and vanished when the script ended. That is tolerable for a smoke test
and useless for a product whose claim is an audit trail.

So each stage writes through here before it moves on. Two consequences are worth
stating, because they are the reason this module exists rather than a final
`INSERT` at the end of the run.

A console can follow a run it did not start. The job holds no session and streams
nothing; the dashboard reads rows. That also means a job that dies mid-run leaves
a truthful record of how far it got, instead of a run that was never recorded.

An external side effect is claimed before it happens, not logged after. A pull
request opened by a job that then crashed must not be opened again on restart,
and only a row written *before* the GitHub call can prevent that.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from packages.schemas.run_state import RunState, assert_transition, is_resumable, is_terminal

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

log = logging.getLogger(__name__)

MAX_TRACE_BODY_CHARS: Final[int] = 4000
MAX_REASON_CHARS: Final[int] = 500
# Enough for a failing test run, short of pushing a page of scrollback through
# every dashboard poll. Anything larger belongs in object storage with a uri.
MAX_ARTIFACT_BODY_CHARS: Final[int] = 60_000

CONSOLE_ACTOR: Final[str] = "console"


@dataclass(frozen=True, slots=True)
class RunHandle:
    """A run the caller may now act on."""

    run_id: str
    state: RunState
    repository: str
    base_sha: str
    # Whether the caller should dispatch execution. False when a run is already
    # in flight, which is what stops a second click from opening a second pull
    # request for the same migration.
    dispatch: bool


_OPEN_SQL: Final[str] = """
INSERT INTO remediation_runs (change_event_id, project_id, repository, base_sha, trace_id)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (change_event_id, project_id, repository) DO NOTHING
RETURNING id, state::text AS state, repository, base_sha
"""

_READ_EXISTING_SQL: Final[str] = """
SELECT id, state::text AS state, repository, base_sha
FROM remediation_runs
WHERE change_event_id = $1 AND project_id = $2 AND repository = $3
"""

# A restart is deliberately not a transition. `FAILED` is terminal and the state
# machine is right to forbid a move out of it; beginning again is a different
# act, recorded with the state it came from so the history still reads honestly.
#
# The attempt budget resets too. A run that paused for a missing key spent no
# attempt on the merits of its patch, and charging it for the pause would mean
# the operator supplies the key only to watch the run give up early.
_RESTART_SQL: Final[str] = """
UPDATE remediation_runs
SET state = 'RECEIVED', failure_reason = '', ended_at = NULL, attempts_used = 0,
    base_sha = CASE WHEN $2 <> '' THEN $2 ELSE base_sha END,
    trace_id = CASE WHEN $3 <> '' THEN $3 ELSE trace_id END,
    updated_at = now()
WHERE id = $1
RETURNING id, state::text AS state, repository, base_sha
"""

# The worklog is what the run is doing now, so a restart starts a new one.
# Keeping the old lines would interleave two executions in the console under one
# set of sequence numbers, each labelled with whatever state was current when it
# was written — which is how a finished run comes to look like it is still
# reading files. What actually happened is not lost: `run_state_transitions`,
# `patch_attempts`, `audit_events` and any pull request survive a restart,
# because those record consequences rather than progress.
_CLEAR_TRACE_SQL: Final[str] = "DELETE FROM run_trace_events WHERE run_id = $1"

# The evidence bundle goes with it, for the same reason and a sharper one: the
# console shows *the* diff and *the* build log for a run, so three restarts left
# three diffs with no way to tell which belongs to the patch the reviewer is
# being asked to trust. A superseded diff is not history, it is a wrong answer
# to "what does this run propose".
_CLEAR_ARTIFACTS_SQL: Final[str] = "DELETE FROM artifacts WHERE run_id = $1"

# Said after the fact, because the sentence and the move are produced by
# different things. The orchestrator advances the machine as it goes and only
# knows how to describe the outcome once the slice returns, so the reason is
# written last rather than guessed at the moment of the transition.
_EXPLAIN_SQL: Final[str] = """
UPDATE remediation_runs
SET failure_reason = $2, updated_at = now()
WHERE id = $1 AND COALESCE(failure_reason, '') = ''
"""

_LOCK_SQL: Final[str] = """
SELECT state::text AS state FROM remediation_runs WHERE id = $1 FOR UPDATE
"""

_ADVANCE_SQL: Final[str] = """
UPDATE remediation_runs
SET state = $2::run_state,
    updated_at = now(),
    failure_reason = CASE WHEN $3 <> '' THEN $3 ELSE failure_reason END,
    ended_at = CASE WHEN $4 THEN now() ELSE ended_at END
WHERE id = $1
"""

_TRANSITION_SQL: Final[str] = """
INSERT INTO run_state_transitions (run_id, sequence, from_state, to_state, actor, reason)
VALUES (
    $1,
    (SELECT COALESCE(max(sequence), 0) + 1 FROM run_state_transitions WHERE run_id = $1),
    $2::run_state, $3::run_state, $4, $5
)
"""

_TRACE_SQL: Final[str] = """
INSERT INTO run_trace_events (
    run_id, sequence, state, kind, verb, body, tool_type, tool_use_id, file_path
)
VALUES (
    $1,
    (SELECT COALESCE(max(sequence), 0) + 1 FROM run_trace_events WHERE run_id = $1),
    $2::run_state, $3, $4, $5, $6, $7, $8
)
"""

_POLICY_SQL: Final[str] = """
INSERT INTO policy_decisions (
    run_id, decision, risk, auto_patch, auto_pr, human_review_required,
    forbidden_globs, required_checks, rule_ids, reason, policy_version
)
VALUES ($1, $2::policy_outcome, $3, $4, $5, $6, $7::text[], $8::text[], $9::text[], $10, $11)
"""

_BEGIN_ATTEMPT_SQL: Final[str] = """
INSERT INTO patch_attempts (
    run_id, attempt_number, patch_agent, patch_model, prompt_version, sandbox_ref
)
VALUES (
    $1,
    (SELECT COALESCE(max(attempt_number), 0) + 1 FROM patch_attempts WHERE run_id = $1),
    $2, $3, $4, $5
)
RETURNING id, attempt_number
"""

_FINISH_ATTEMPT_SQL: Final[str] = """
UPDATE patch_attempts
SET status = $2::attempt_status,
    build_exit_code = $3,
    test_exit_code = $4,
    files_changed = $5::text[],
    diff_sha256 = $6,
    failure_summary = $7,
    ended_at = now()
WHERE id = $1
"""

# Counted forward rather than recounted from `patch_attempts`, because that
# table keeps every attempt the row has ever seen. Recounting would charge a
# restarted run for the attempts that already failed, and an operator who asks
# for a second try would get a budget that was already spent.
_COUNT_ATTEMPTS_SQL: Final[str] = """
UPDATE remediation_runs
SET attempts_used = attempts_used + 1, updated_at = now()
WHERE id = $1
"""

_VERIFICATION_SQL: Final[str] = """
INSERT INTO verification_results (
    run_id, patch_attempt_id, verdict, verifier_agent, verifier_model,
    patch_agent, patch_model, checks, evidence_summary
)
VALUES ($1, $2, $3::verdict, $4, $5, $6, $7, $8::jsonb, $9)
"""

_ARTIFACT_SQL: Final[str] = """
INSERT INTO artifacts (
    run_id, patch_attempt_id, kind, uri, content_sha256, size_bytes, media_type, body
)
VALUES ($1, $2, $3::evidence_kind, $4, $5, $6, $7, $8)
"""

_PR_SQL: Final[str] = """
INSERT INTO pull_requests (
    run_id, number, url, title, head_branch, base_branch, head_sha, state
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8::pr_state)
ON CONFLICT (run_id) DO UPDATE
SET number = EXCLUDED.number, url = EXCLUDED.url, state = EXCLUDED.state,
    head_sha = EXCLUDED.head_sha, observed_at = now()
"""

# `DO NOTHING` plus a row count is the whole mechanism: the first caller inserts
# and is allowed to act, every later caller conflicts and is not.
_CLAIM_SQL: Final[str] = """
INSERT INTO idempotency_keys (run_id, action_type, base_sha)
VALUES ($1, $2, $3)
ON CONFLICT (run_id, action_type, base_sha) DO NOTHING
RETURNING run_id
"""

_FULFIL_SQL: Final[str] = """
UPDATE idempotency_keys SET result_ref = $4
WHERE run_id = $1 AND action_type = $2 AND base_sha = $3
"""

_AUDIT_SQL: Final[str] = """
INSERT INTO audit_events (
    actor, action, target, outcome, reason, trace_id, run_id, project_id, repository
)
VALUES ($1, $2, $3, $4::audit_outcome, $5, $6, $7, $8, $9)
"""


async def open_run(
    connection: asyncpg.Connection,
    *,
    change_event_id: UUID | str,
    project_id: UUID | str,
    repository: str,
    base_sha: str = "",
    trace_id: str = "",
) -> RunHandle:
    """Return the run for this change and repository, creating or restarting it.

    Idempotent by design rather than by luck. A run already in flight is returned
    with `dispatch` false so the caller starts no second execution; a run that
    ended, or that is paused waiting on the operator, is begun again on the same
    row, keeping one stable id per card in the console and one history to read.
    """
    change_uuid = _uuid(change_event_id)
    project_uuid = _uuid(project_id)

    row = await connection.fetchrow(
        _OPEN_SQL, change_uuid, project_uuid, repository, base_sha, trace_id
    )
    if row is not None:
        await _transition(
            connection, row["id"], None, RunState.RECEIVED, CONSOLE_ACTOR, "run requested"
        )
        return _handle(row, dispatch=True)

    existing = await connection.fetchrow(_READ_EXISTING_SQL, change_uuid, project_uuid, repository)
    if existing is None:  # pragma: no cover - conflict implies the row is there
        raise RuntimeError(f"could not open a run for {repository}")

    state = RunState(existing["state"])
    # Paused is not the same as running. A run parked on a missing secret has no
    # execution behind it, so refusing to dispatch would strand it: the operator
    # supplies the key, presses continue, and nothing ever picks the run up.
    if not is_terminal(state) and not is_resumable(state):
        return _handle(existing, dispatch=False)

    restarted = await connection.fetchrow(_RESTART_SQL, existing["id"], base_sha, trace_id)
    await connection.execute(_CLEAR_TRACE_SQL, existing["id"])
    await connection.execute(_CLEAR_ARTIFACTS_SQL, existing["id"])
    await _transition(
        connection,
        existing["id"],
        state,
        RunState.RECEIVED,
        CONSOLE_ACTOR,
        "resumed" if is_resumable(state) else "restarted",
    )
    return _handle(restarted, dispatch=True)


async def advance(
    connection: asyncpg.Connection,
    run_id: UUID | str,
    to_state: RunState,
    *,
    actor: str,
    reason: str = "",
) -> RunState:
    """Move a run, refusing any move the state machine forbids.

    The current state is read under a row lock so that the check and the write
    cannot straddle another writer. `assert_transition` raises before anything is
    persisted, which is what keeps an illegal move out of the history rather than
    merely out of the summary.
    """
    identifier = _uuid(run_id)
    async with connection.transaction():
        row = await connection.fetchrow(_LOCK_SQL, identifier)
        if row is None:
            raise LookupError(f"no run {run_id}")
        source = RunState(row["state"])
        assert_transition(source, to_state)

        trimmed = reason.strip()[:MAX_REASON_CHARS]
        failure = trimmed if to_state is RunState.FAILED else ""
        await connection.execute(
            _ADVANCE_SQL, identifier, str(to_state), failure, is_terminal(to_state)
        )
        await _transition(connection, identifier, source, to_state, actor, trimmed)

    log.info("run %s %s -> %s (%s)", run_id, source, to_state, actor)
    return to_state


async def append_trace(
    connection: asyncpg.Connection,
    run_id: UUID | str,
    *,
    state: RunState,
    kind: str,
    body: str,
    verb: str = "",
    tool_type: str = "",
    tool_use_id: str = "",
    file_path: str = "",
) -> None:
    """Record one line of the agent worklog."""
    await connection.execute(
        _TRACE_SQL,
        _uuid(run_id),
        str(state),
        kind,
        verb,
        body.strip()[:MAX_TRACE_BODY_CHARS],
        tool_type,
        tool_use_id,
        file_path,
    )


async def explain(connection: asyncpg.Connection, run_id: UUID | str, reason: str) -> None:
    """Record why a run ended the way it did, if nothing has said yet.

    Left to the transition alone the console shows a run that stopped with no
    stated cause, which is the least useful thing a stopped run can show.
    """
    trimmed = reason.strip()[:MAX_REASON_CHARS]
    if trimmed:
        await connection.execute(_EXPLAIN_SQL, _uuid(run_id), trimmed)


async def record_policy(
    connection: asyncpg.Connection,
    run_id: UUID | str,
    *,
    decision: str,
    risk: str = "",
    auto_patch: bool = False,
    auto_pr: bool = False,
    human_review_required: bool = True,
    forbidden_globs: list[str] | None = None,
    required_checks: list[str] | None = None,
    rule_ids: list[str] | None = None,
    reason: str = "",
    policy_version: str = "",
) -> None:
    """Record what policy decided. `auto_merge` is absent because it cannot be true."""
    await connection.execute(
        _POLICY_SQL,
        _uuid(run_id),
        decision,
        risk,
        auto_patch,
        auto_pr,
        human_review_required,
        list(forbidden_globs or []),
        list(required_checks or []),
        list(rule_ids or []),
        reason.strip()[:MAX_REASON_CHARS],
        policy_version,
    )


async def begin_attempt(
    connection: asyncpg.Connection,
    run_id: UUID | str,
    *,
    patch_agent: str = "",
    patch_model: str = "",
    prompt_version: str = "",
    sandbox_ref: str = "",
) -> tuple[str, int]:
    """Open a patch attempt and return its id and number."""
    identifier = _uuid(run_id)
    row = await connection.fetchrow(
        _BEGIN_ATTEMPT_SQL, identifier, patch_agent, patch_model, prompt_version, sandbox_ref
    )
    await connection.execute(_COUNT_ATTEMPTS_SQL, identifier)
    return str(row["id"]), int(row["attempt_number"])


async def finish_attempt(
    connection: asyncpg.Connection,
    attempt_id: UUID | str,
    *,
    status: str,
    build_exit_code: int | None = None,
    test_exit_code: int | None = None,
    files_changed: list[str] | None = None,
    diff_sha256: str = "",
    failure_summary: str = "",
) -> None:
    await connection.execute(
        _FINISH_ATTEMPT_SQL,
        _uuid(attempt_id),
        status,
        build_exit_code,
        test_exit_code,
        list(files_changed or []),
        diff_sha256,
        failure_summary.strip()[:MAX_REASON_CHARS],
    )


async def record_verification(
    connection: asyncpg.Connection,
    run_id: UUID | str,
    *,
    verdict: str,
    checks: list[dict[str, Any]] | None = None,
    verifier_agent: str = "",
    verifier_model: str = "",
    patch_agent: str = "",
    patch_model: str = "",
    evidence_summary: str = "",
    patch_attempt_id: UUID | str | None = None,
) -> None:
    """Record the independent verdict, and who reached it.

    Both agents are stored so a reviewer can see they differ. A verifier that
    turned out to be the patch author is a finding, not a detail.
    """
    await connection.execute(
        _VERIFICATION_SQL,
        _uuid(run_id),
        None if patch_attempt_id is None else _uuid(patch_attempt_id),
        verdict,
        verifier_agent,
        verifier_model,
        patch_agent,
        patch_model,
        list(checks or []),
        evidence_summary.strip()[:MAX_REASON_CHARS],
    )


async def record_artifact(
    connection: asyncpg.Connection,
    run_id: UUID | str,
    *,
    kind: str,
    body: str = "",
    uri: str = "",
    content_sha256: str = "",
    media_type: str = "text/plain",
    patch_attempt_id: UUID | str | None = None,
) -> None:
    trimmed = body[:MAX_ARTIFACT_BODY_CHARS]
    await connection.execute(
        _ARTIFACT_SQL,
        _uuid(run_id),
        None if patch_attempt_id is None else _uuid(patch_attempt_id),
        kind,
        uri,
        content_sha256,
        len(body.encode("utf-8")),
        media_type,
        trimmed,
    )


async def record_pull_request(
    connection: asyncpg.Connection,
    run_id: UUID | str,
    *,
    number: int,
    url: str,
    head_branch: str,
    base_branch: str,
    title: str = "",
    head_sha: str = "",
    state: str = "open",
) -> None:
    await connection.execute(
        _PR_SQL,
        _uuid(run_id),
        number,
        url,
        title,
        head_branch,
        base_branch,
        head_sha,
        state,
    )


async def claim(
    connection: asyncpg.Connection, run_id: UUID | str, action: str, base_sha: str
) -> bool:
    """Take the right to perform one external action once.

    Called before the side effect. A caller that gets False must not act: some
    earlier execution of this run already did, and the pull request it opened is
    the one that counts.
    """
    row = await connection.fetchrow(_CLAIM_SQL, _uuid(run_id), action, base_sha)
    return row is not None


async def fulfil(
    connection: asyncpg.Connection, run_id: UUID | str, action: str, base_sha: str, result: str
) -> None:
    """Record what the claimed action produced."""
    await connection.execute(_FULFIL_SQL, _uuid(run_id), action, base_sha, result)


async def audit(
    connection: asyncpg.Connection,
    *,
    actor: str,
    action: str,
    outcome: str,
    target: str = "",
    reason: str = "",
    trace_id: str = "",
    run_id: UUID | str | None = None,
    project_id: UUID | str | None = None,
    repository: str | None = None,
) -> None:
    """Record a privileged act. Denials matter more than successes."""
    await connection.execute(
        _AUDIT_SQL,
        actor,
        action,
        target,
        outcome,
        reason.strip()[:MAX_REASON_CHARS],
        trace_id,
        None if run_id is None else _uuid(run_id),
        None if project_id is None else _uuid(project_id),
        repository,
    )


# ------------------------------------------------------------------- reads ---

# The commit an assessment was actually reached at is better than the one the
# index happens to hold now: a run must reason about the tree its findings
# describe, not a newer one nobody has looked at.
_TARGET_SQL: Final[str] = """
SELECT
    ce.id                                   AS change_event_id,
    ce.external_id                          AS external_id,
    COALESCE(
        $3::text,
        (
            SELECT ci.repository FROM change_impacts ci
            WHERE ci.change_event_id = ce.id AND ci.project_id = $2 AND ci.affected
            ORDER BY ci.assessed_at DESC LIMIT 1
        ),
        (
            SELECT u.repository
            FROM provider_usages u
            JOIN project_repositories pr ON pr.full_name = u.repository
            WHERE pr.project_id = $2
              AND u.retired_at IS NULL
              AND u.identifier = ANY (ce.affected_identifiers)
            GROUP BY u.repository
            ORDER BY count(*) DESC LIMIT 1
        )
    )                                       AS repository
FROM change_events ce
WHERE ce.external_id = $1
ORDER BY ce.detected_at DESC
LIMIT 1
"""

_BASE_SHA_SQL: Final[str] = """
SELECT COALESCE(
    (
        SELECT ci.base_sha FROM change_impacts ci
        WHERE ci.change_event_id = $1 AND ci.project_id = $2 AND ci.repository = $3
          AND ci.base_sha <> ''
        ORDER BY ci.assessed_at DESC LIMIT 1
    ),
    (
        SELECT s.indexed_sha FROM repo_index_state s
        WHERE s.repository = $3 AND COALESCE(s.indexed_sha, '') <> ''
        ORDER BY s.last_full_index DESC NULLS LAST LIMIT 1
    ),
    ''
) AS base_sha
"""

_LIST_SQL: Final[str] = """
SELECT
    r.id::text                  AS run_id,
    r.state::text               AS state,
    r.repository                AS repository,
    ce.external_id              AS change_id,
    r.base_sha                  AS base_sha,
    r.attempts_used             AS attempts_used,
    r.attempt_budget            AS attempt_budget,
    NULLIF(r.failure_reason,'') AS failure_reason,
    r.started_at                AS started_at,
    r.updated_at                AS updated_at,
    r.ended_at                  AS ended_at,
    pr.url                      AS pull_request_url,
    pr.number                   AS pull_request_number
FROM remediation_runs r
JOIN change_events ce ON ce.id = r.change_event_id
LEFT JOIN pull_requests pr ON pr.run_id = r.id
WHERE r.project_id = $1
ORDER BY r.started_at DESC
LIMIT $2
"""

_DETAIL_SQL: Final[str] = _LIST_SQL.replace(
    "WHERE r.project_id = $1\nORDER BY r.started_at DESC\nLIMIT $2",
    "WHERE r.project_id = $1 AND r.id = $2",
)

_TRACE_READ_SQL: Final[str] = """
SELECT sequence, state::text AS state, kind, verb, body, tool_type, tool_use_id,
       file_path, occurred_at
FROM run_trace_events
WHERE run_id = $1 AND sequence > $2
ORDER BY sequence
"""

_TRANSITIONS_READ_SQL: Final[str] = """
SELECT sequence, from_state::text AS from_state, to_state::text AS to_state,
       actor, reason, occurred_at
FROM run_state_transitions
WHERE run_id = $1
ORDER BY sequence
"""

_POLICY_READ_SQL: Final[str] = """
SELECT decision::text AS decision, risk, auto_patch, auto_pr, auto_merge,
       human_review_required, forbidden_globs, required_checks, reason,
       policy_version, evaluated_at
FROM policy_decisions WHERE run_id = $1 ORDER BY evaluated_at DESC LIMIT 1
"""

_VERIFICATION_READ_SQL: Final[str] = """
SELECT verdict::text AS verdict, verifier_agent, verifier_model, patch_agent,
       patch_model, checks, evidence_summary, evaluated_at
FROM verification_results WHERE run_id = $1 ORDER BY evaluated_at DESC LIMIT 1
"""

_ARTIFACTS_READ_SQL: Final[str] = """
SELECT kind::text AS kind, uri, content_sha256, size_bytes, media_type, body, created_at
FROM artifacts WHERE run_id = $1 ORDER BY created_at, kind
"""

_PR_READ_SQL: Final[str] = """
SELECT number, url, title, head_branch, base_branch, head_sha, state::text AS state,
       merged_by_patchapi, opened_at
FROM pull_requests WHERE run_id = $1
"""


async def resolve_target(
    connection: asyncpg.Connection,
    *,
    external_id: str,
    project_id: UUID | str,
    repository: str = "",
) -> tuple[UUID, str, str] | None:
    """The change, repository and commit a run for `external_id` would be about.

    Returns None when the change is unknown, and an empty repository when this
    project has nothing that uses it — neither is an error, and both are
    answered as "there is nothing to remediate" rather than guessed at.
    """
    project_uuid = _uuid(project_id)
    row = await connection.fetchrow(
        _TARGET_SQL, external_id, project_uuid, repository.strip() or None
    )
    if row is None:
        return None
    resolved = str(row["repository"] or "")
    if not resolved:
        return row["change_event_id"], "", ""
    base_sha = await connection.fetchval(
        _BASE_SHA_SQL, row["change_event_id"], project_uuid, resolved
    )
    return row["change_event_id"], resolved, str(base_sha or "")


async def list_runs(
    connection: asyncpg.Connection, *, project_id: UUID | str, limit: int = 50
) -> list[dict[str, Any]]:
    rows = await connection.fetch(_LIST_SQL, _uuid(project_id), limit)
    return [dict(row) for row in rows]


async def read_run(
    connection: asyncpg.Connection,
    *,
    project_id: UUID | str,
    run_id: UUID | str,
    since: int = 0,
) -> dict[str, Any] | None:
    """One run and everything recorded about it.

    `since` is the highest trace sequence the caller already holds. The console
    polls, and a run that produces hundreds of worklog lines should not resend
    all of them every second — the sequence is dense and monotonic, so asking for
    what comes after it is exact rather than a timestamp heuristic.
    """
    identifier = _uuid(run_id)
    summary = await connection.fetchrow(_DETAIL_SQL, _uuid(project_id), identifier)
    if summary is None:
        return None

    trace = await connection.fetch(_TRACE_READ_SQL, identifier, max(since, 0))
    transitions = await connection.fetch(_TRANSITIONS_READ_SQL, identifier)
    policy = await connection.fetchrow(_POLICY_READ_SQL, identifier)
    verification = await connection.fetchrow(_VERIFICATION_READ_SQL, identifier)
    artifacts = await connection.fetch(_ARTIFACTS_READ_SQL, identifier)
    pull_request = await connection.fetchrow(_PR_READ_SQL, identifier)

    return {
        **dict(summary),
        "trace": [dict(row) for row in trace],
        "transitions": [dict(row) for row in transitions],
        "policy": None if policy is None else dict(policy),
        "verification": None if verification is None else dict(verification),
        "artifacts": [dict(row) for row in artifacts],
        "pull_request": None if pull_request is None else dict(pull_request),
    }


async def _transition(
    connection: asyncpg.Connection,
    run_id: UUID,
    source: RunState | None,
    target: RunState,
    actor: str,
    reason: str,
) -> None:
    await connection.execute(
        _TRANSITION_SQL,
        run_id,
        None if source is None else str(source),
        str(target),
        actor,
        reason,
    )


def _handle(row: Any, *, dispatch: bool) -> RunHandle:
    return RunHandle(
        run_id=str(row["id"]),
        state=RunState(row["state"]),
        repository=row["repository"],
        base_sha=row["base_sha"],
        dispatch=dispatch,
    )


def _uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


__all__ = [
    "CONSOLE_ACTOR",
    "MAX_ARTIFACT_BODY_CHARS",
    "MAX_TRACE_BODY_CHARS",
    "RunHandle",
    "advance",
    "append_trace",
    "audit",
    "begin_attempt",
    "claim",
    "finish_attempt",
    "fulfil",
    "list_runs",
    "open_run",
    "read_run",
    "record_artifact",
    "record_policy",
    "record_pull_request",
    "record_verification",
    "resolve_target",
]
