"""The dashboard's read projections over authoritative state.

Every method here is a query and nothing else. The projections are assembled in
Python from several small indexed reads rather than one wide join, because the
alternative — aggregating composite rows in SQL — makes the shape of a page
depend on a query plan that is hard to read and harder to change.

Two rules hold throughout:

*Absence is reported as absence.* An unknown run returns `None`. A repository
with no inventoried usage is returned with a zero count and `affected` false,
not omitted — "we looked and found nothing" is a weaker claim than "we did not
look", and the organization view has to distinguish them.

*Staleness is reported, not hidden.* Findings carry the commit they were
observed at. A count built from an old index is evidence about an old commit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from patchapi_control_api.ports import (
    ArtifactRecord,
    AuditEventRecord,
    ChangeRecord,
    FleetActorRecord,
    FleetSnapshotRecord,
    PatchAttemptRecord,
    PolicyDecisionRecord,
    PullRequestRecord,
    RepositoryImpactRecord,
    RunDetailRecord,
    RunSummaryRecord,
    TransitionRecord,
    UsageRecord,
    VerificationCheckRecord,
    VerificationRecord,
)

from packages.state.pool import StateUnavailableError

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

# ------------------------------------------------------------------ changes ---

# `affected_repositories` counts the inventory, not the runs: a repository is
# exposed the moment a usage matches, whether or not a run has been started for
# it yet. Counting runs instead would report zero exposure for a change nobody
# has acted on, which is exactly the case the dashboard exists to surface.
_CHANGE_COLUMNS = """
    ce.external_id                          AS change_id,
    ce.provider                             AS provider,
    ce.change_kind::text                    AS change_kind,
    COALESCE(NULLIF(ce.title, ''), ce.external_id) AS title,
    ce.source_urls                          AS source_urls,
    NULLIF(ce.source_sha256, '')            AS source_sha256,
    ce.affected_identifiers                 AS affected_identifiers,
    (
        SELECT i.identifier
        FROM change_event_identifiers i
        WHERE i.change_event_id = ce.id AND i.role = 'replacement'
        LIMIT 1
    )                                       AS recommended_replacement,
    ce.effective_at                         AS effective_at,
    ce.detected_at                          AS detected_at,
    (
        SELECT count(DISTINCT u.repository)
        FROM provider_usages u
        WHERE u.retired_at IS NULL
          AND u.identifier = ANY (ce.affected_identifiers)
    )::int                                  AS affected_repositories,
    (
        SELECT count(*)
        FROM remediation_runs r
        WHERE r.change_event_id = ce.id
          AND r.state NOT IN (
              'UNAFFECTED', 'HUMAN_REQUIRED', 'BLOCKED', 'FAILED', 'PR_CREATED'
          )
    )::int                                  AS open_runs,
    (
        SELECT count(*) FROM remediation_runs r WHERE r.change_event_id = ce.id
    )::int                                  AS total_runs
"""

_LIST_CHANGES = f"""
SELECT {_CHANGE_COLUMNS}
FROM change_events ce
ORDER BY ce.detected_at DESC
LIMIT $1
"""

# Re-polling a changed page creates a second event with the same external id, so
# the newest detection is the current one.
_READ_CHANGE = f"""
SELECT {_CHANGE_COLUMNS}
FROM change_events ce
WHERE ce.external_id = $1
ORDER BY ce.detected_at DESC
LIMIT 1
"""

_RESOLVE_CHANGE = """
SELECT id, affected_identifiers
FROM change_events
WHERE external_id = $1
ORDER BY detected_at DESC
LIMIT 1
"""

_CHANGE_FOR_RUN = f"""
SELECT {_CHANGE_COLUMNS}
FROM change_events ce
WHERE ce.id = (SELECT change_event_id FROM remediation_runs WHERE id = $1::uuid)
"""

# ------------------------------------------------------------------- impact ---

# A NULL identifier filter means "every identifier in the inventory"; a non-NULL
# one scopes the counts to a single change.
# The repository universe is the inventory itself. There is no `repositories`
# table: a repository is known to PatchAPI because something indexed it, and
# `provider_usages.repository` is where that fact lives. `owner_team` and
# `criticality` have no source yet, so they are reported as unknown rather than
# invented — a dashboard that shows a made-up criticality is worse than one that
# admits it does not know.
_LIST_REPOSITORIES = """
WITH known AS (
    SELECT DISTINCT repository FROM provider_usages WHERE retired_at IS NULL
),
indexed AS (
    SELECT DISTINCT ON (repository)
        repository,
        NULLIF(indexed_sha, '') AS indexed_sha,
        GREATEST(last_full_index, COALESCE(last_delta_index, last_full_index)) AS indexed_at
    FROM repo_index_state
    ORDER BY repository, last_full_index DESC NULLS LAST
)
SELECT
    k.repository                                        AS repository,
    NULL::text                                          AS owner_team,
    'unknown'                                           AS criticality,
    i.indexed_sha                                       AS indexed_sha,
    i.indexed_at                                        AS indexed_at,
    COALESCE(u.usage_count, 0)::int                     AS usage_count,
    COALESCE(u.file_count, 0)::int                      AS file_count,
    COALESCE(u.identifiers, ARRAY[]::text[])            AS identifiers
FROM known k
LEFT JOIN indexed i ON i.repository = k.repository
LEFT JOIN LATERAL (
    SELECT
        count(*)                        AS usage_count,
        count(DISTINCT file_path)       AS file_count,
        array_agg(DISTINCT identifier)  AS identifiers
    FROM provider_usages
    WHERE repository = k.repository
      AND retired_at IS NULL
      AND ($1::text[] IS NULL OR identifier = ANY ($1::text[]))
) u ON TRUE
ORDER BY COALESCE(u.usage_count, 0) DESC, k.repository
"""

_LIST_USAGES = """
SELECT
    u.repository                AS repository,
    u.identifier                AS identifier,
    u.surface                   AS surface,
    u.file_path                 AS file_path,
    u.line_start                AS line_start,
    u.line_end                  AS line_end,
    u.detection_layer::text     AS detection_layer,
    u.confidence                AS confidence,
    u.observed_sha              AS observed_sha
FROM provider_usages u
WHERE u.retired_at IS NULL
  AND ($1::text[] IS NULL OR u.identifier = ANY ($1::text[]))
ORDER BY u.repository, u.file_path, u.line_start
"""

_LATEST_RUN_PER_REPOSITORY = """
SELECT DISTINCT ON (r.repository)
    r.repository                AS repository,
    r.id::text                  AS run_id,
    r.state::text               AS state
FROM remediation_runs r
WHERE ($1::uuid IS NULL OR r.change_event_id = $1::uuid)
ORDER BY r.repository, r.started_at DESC
"""

# --------------------------------------------------------------------- runs ---

_RUN_COLUMNS = """
    r.id::text                      AS run_id,
    r.state::text                   AS state,
    r.repository                    AS repository,
    ce.external_id                  AS change_id,
    r.base_sha                      AS base_sha,
    NULLIF(r.trace_id, '')          AS trace_id,
    r.attempts_used                 AS attempts_used,
    r.attempt_budget                AS attempt_budget,
    r.started_at                    AS started_at,
    r.updated_at                    AS updated_at,
    r.ended_at                      AS ended_at,
    NULLIF(r.failure_reason, '')    AS failure_reason
"""

_LIST_RUNS = f"""
SELECT {_RUN_COLUMNS}
FROM remediation_runs r
JOIN change_events ce ON ce.id = r.change_event_id
WHERE ($1::text IS NULL OR ce.external_id = $1::text)
  AND ($2::text IS NULL OR r.repository = $2::text)
ORDER BY r.started_at DESC
LIMIT $3
"""

_READ_RUN_SUMMARY = f"""
SELECT {_RUN_COLUMNS}
FROM remediation_runs r
JOIN change_events ce ON ce.id = r.change_event_id
WHERE r.id = $1::uuid
"""

_READ_TRANSITIONS = """
SELECT
    sequence            AS sequence,
    from_state::text    AS from_state,
    to_state::text      AS to_state,
    actor               AS actor,
    reason              AS reason,
    occurred_at         AS occurred_at
FROM run_state_transitions
WHERE run_id = $1::uuid
ORDER BY sequence
"""

_READ_POLICY = """
SELECT
    decision::text      AS decision,
    risk::text          AS risk,
    auto_patch          AS auto_patch,
    auto_pr             AS auto_pr,
    auto_merge          AS auto_merge,
    forbidden_globs     AS forbidden_globs,
    required_checks     AS required_checks,
    reason              AS reason,
    policy_version      AS policy_version,
    evaluated_at        AS evaluated_at
FROM policy_decisions
WHERE run_id = $1::uuid
ORDER BY evaluated_at DESC
LIMIT 1
"""

_READ_ATTEMPTS = """
SELECT
    attempt_number      AS attempt_number,
    status::text        AS status,
    patch_agent         AS patch_agent,
    patch_model         AS patch_model,
    prompt_version      AS prompt_version,
    sandbox_ref         AS sandbox_ref,
    build_exit_code     AS build_exit_code,
    test_exit_code      AS test_exit_code,
    diff_sha256         AS diff_sha256,
    files_changed       AS files_changed,
    failure_summary     AS failure_summary,
    started_at          AS started_at,
    ended_at            AS ended_at
FROM patch_attempts
WHERE run_id = $1::uuid
ORDER BY attempt_number
"""

_READ_VERIFICATION = """
SELECT
    v.verdict::text     AS verdict,
    v.verifier_agent    AS verifier_agent,
    v.verifier_model    AS verifier_model,
    v.patch_agent       AS patch_agent,
    v.patch_model       AS patch_model,
    v.checks            AS checks,
    v.evidence_summary  AS evidence_summary,
    v.evaluated_at      AS evaluated_at,
    pa.attempt_number   AS attempt_number
FROM verification_results v
JOIN patch_attempts pa ON pa.id = v.patch_attempt_id
WHERE v.run_id = $1::uuid
ORDER BY v.evaluated_at DESC
LIMIT 1
"""

_READ_ARTIFACTS = """
SELECT
    a.kind::text        AS kind,
    a.uri               AS uri,
    a.content_sha256    AS content_sha256,
    a.size_bytes        AS size_bytes,
    a.media_type        AS media_type,
    pa.attempt_number   AS attempt_number,
    a.created_at        AS created_at
FROM artifacts a
LEFT JOIN patch_attempts pa ON pa.id = a.patch_attempt_id
WHERE a.run_id = $1::uuid
ORDER BY a.created_at, a.kind
"""

_READ_PULL_REQUEST = """
SELECT
    number              AS number,
    url                 AS url,
    title               AS title,
    head_branch         AS head_branch,
    base_branch         AS base_branch,
    head_sha            AS head_sha,
    state::text         AS state,
    merged_by_patchapi  AS merged_by_patchapi,
    opened_at           AS opened_at,
    observed_at         AS observed_at
FROM pull_requests
WHERE run_id = $1::uuid
"""

_READ_RUN_USAGES = """
SELECT
    u.identifier            AS identifier,
    u.surface               AS surface,
    u.file_path             AS file_path,
    u.line_start            AS line_start,
    u.line_end              AS line_end,
    u.detection_layer::text AS detection_layer,
    u.confidence            AS confidence,
    u.observed_sha          AS observed_sha
FROM provider_usages u
JOIN remediation_runs r ON r.repository = u.repository
JOIN change_events ce ON ce.id = r.change_event_id
WHERE r.id = $1::uuid
  AND u.retired_at IS NULL
  AND u.identifier = ANY (ce.affected_identifiers)
ORDER BY u.file_path, u.line_start
"""

# -------------------------------------------------------------------- fleet ---

_FLEET_ACTORS = """
SELECT
    actor                                                   AS actor,
    array_agg(DISTINCT action)                              AS actions,
    count(*) FILTER (WHERE outcome = 'SUCCEEDED')::int      AS succeeded,
    count(*) FILTER (WHERE outcome = 'DENIED')::int         AS denied,
    count(*) FILTER (WHERE outcome = 'FAILED')::int         AS failed,
    max(occurred_at)                                        AS last_seen_at
FROM audit_events
GROUP BY actor
ORDER BY max(occurred_at) DESC
"""

# Which model each agent actually reasoned with, taken from the rows that record
# it rather than from configuration — configuration says what should have run.
_FLEET_MODELS = """
SELECT patch_agent AS actor, patch_model AS model FROM patch_attempts
UNION
SELECT verifier_agent AS actor, verifier_model AS model FROM verification_results
"""

_FLEET_DENIALS = """
SELECT
    ae.actor                    AS actor,
    ae.action                   AS action,
    NULLIF(ae.target, '')       AS target,
    ae.outcome::text            AS outcome,
    NULLIF(ae.reason, '')       AS reason,
    NULLIF(ae.trace_id, '')     AS trace_id,
    ae.repository               AS repository,
    ae.run_id::text             AS run_id,
    ae.occurred_at              AS occurred_at
FROM audit_events ae
WHERE ae.outcome = 'DENIED'
ORDER BY ae.occurred_at DESC
LIMIT $1
"""

_POLICY_VERSIONS = """
SELECT DISTINCT policy_version FROM policy_decisions ORDER BY policy_version DESC
"""


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _usage(row: Any) -> UsageRecord:
    return UsageRecord(
        identifier=row["identifier"],
        surface=row["surface"],
        file_path=row["file_path"],
        line_start=row["line_start"],
        line_end=row["line_end"],
        detection_layer=row["detection_layer"],
        confidence=float(row["confidence"]),
        observed_sha=row["observed_sha"],
    )


def _checks(payload: Any) -> tuple[VerificationCheckRecord, ...]:
    """Read the named checks out of a stored report.

    Fields are selected explicitly rather than splatted: the report is a JSON
    document that may gain keys over time, and a contract that rejects unknown
    fields would turn that into a 500 on a page whose job is to display it.
    """
    if not isinstance(payload, list):
        return ()
    return tuple(
        VerificationCheckRecord(name=str(entry["name"]), passed=bool(entry["passed"]))
        for entry in payload
        if isinstance(entry, dict) and "name" in entry and "passed" in entry
    )


class PostgresDashboardReader:
    """Serves the dashboard's read projections from authoritative Postgres."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # -- changes ----------------------------------------------------------

    async def list_changes(self, *, limit: int) -> tuple[ChangeRecord, ...]:
        rows = await self._fetch(_LIST_CHANGES, limit)
        return tuple(ChangeRecord(**dict(row)) for row in rows)

    async def read_change(self, change_id: str) -> ChangeRecord | None:
        row = await self._fetchrow(_READ_CHANGE, change_id)
        return None if row is None else ChangeRecord(**dict(row))

    # -- organization impact ----------------------------------------------

    async def list_repository_impact(
        self, *, change_id: str | None
    ) -> tuple[RepositoryImpactRecord, ...]:
        identifiers: list[str] | None = None
        change_uuid: UUID | None = None
        if change_id is not None:
            resolved = await self._fetchrow(_RESOLVE_CHANGE, change_id)
            if resolved is None:
                # An unknown change scopes to nothing rather than silently
                # widening to every identifier in the inventory.
                return ()
            change_uuid = resolved["id"]
            identifiers = list(resolved["affected_identifiers"])

        repository_rows = await self._fetch(_LIST_REPOSITORIES, identifiers)
        usage_rows = await self._fetch(_LIST_USAGES, identifiers)
        run_rows = await self._fetch(_LATEST_RUN_PER_REPOSITORY, change_uuid)

        usages_by_repository: dict[str, list[UsageRecord]] = {}
        for row in usage_rows:
            usages_by_repository.setdefault(row["repository"], []).append(_usage(row))
        runs_by_repository = {row["repository"]: row for row in run_rows}

        records: list[RepositoryImpactRecord] = []
        for row in repository_rows:
            repository = row["repository"]
            run = runs_by_repository.get(repository)
            records.append(
                RepositoryImpactRecord(
                    repository=repository,
                    owner_team=row["owner_team"],
                    criticality=row["criticality"],
                    affected=row["usage_count"] > 0,
                    indexed_sha=row["indexed_sha"],
                    indexed_at=row["indexed_at"],
                    usage_count=row["usage_count"],
                    file_count=row["file_count"],
                    identifiers=tuple(sorted(row["identifiers"])),
                    usages=tuple(usages_by_repository.get(repository, ())),
                    latest_run_id=None if run is None else run["run_id"],
                    latest_run_state=None if run is None else run["state"],
                )
            )
        return tuple(records)

    # -- runs --------------------------------------------------------------

    async def list_runs(
        self, *, change_id: str | None, repository: str | None, limit: int
    ) -> tuple[RunSummaryRecord, ...]:
        rows = await self._fetch(_LIST_RUNS, change_id, repository, limit)
        return tuple(RunSummaryRecord(**dict(row)) for row in rows)

    async def read_run_detail(self, run_id: str) -> RunDetailRecord | None:
        if not _is_uuid(run_id):
            return None
        summary_row = await self._fetchrow(_READ_RUN_SUMMARY, run_id)
        if summary_row is None:
            return None
        change_row = await self._fetchrow(_CHANGE_FOR_RUN, run_id)
        if change_row is None:
            # The schema requires a change event per run, so this means the row
            # vanished between the two reads. Reporting the run as absent is
            # truthful; assembling a detail page around a missing change is not.
            return None

        transition_rows = await self._fetch(_READ_TRANSITIONS, run_id)
        policy_row = await self._fetchrow(_READ_POLICY, run_id)
        attempt_rows = await self._fetch(_READ_ATTEMPTS, run_id)
        verification_row = await self._fetchrow(_READ_VERIFICATION, run_id)
        artifact_rows = await self._fetch(_READ_ARTIFACTS, run_id)
        pull_request_row = await self._fetchrow(_READ_PULL_REQUEST, run_id)
        usage_rows = await self._fetch(_READ_RUN_USAGES, run_id)

        verification: VerificationRecord | None = None
        if verification_row is not None:
            fields = dict(verification_row)
            verification = VerificationRecord(**{**fields, "checks": _checks(fields["checks"])})

        return RunDetailRecord(
            summary=RunSummaryRecord(**dict(summary_row)),
            change=ChangeRecord(**dict(change_row)),
            transitions=tuple(TransitionRecord(**dict(row)) for row in transition_rows),
            policy=None if policy_row is None else PolicyDecisionRecord(**dict(policy_row)),
            attempts=tuple(PatchAttemptRecord(**dict(row)) for row in attempt_rows),
            verification=verification,
            artifacts=tuple(ArtifactRecord(**dict(row)) for row in artifact_rows),
            pull_request=(
                None if pull_request_row is None else PullRequestRecord(**dict(pull_request_row))
            ),
            usages=tuple(_usage(row) for row in usage_rows),
        )

    # -- fleet -------------------------------------------------------------

    async def read_fleet_snapshot(self, *, limit: int) -> FleetSnapshotRecord:
        actor_rows = await self._fetch(_FLEET_ACTORS)
        model_rows = await self._fetch(_FLEET_MODELS)
        denial_rows = await self._fetch(_FLEET_DENIALS, limit)
        version_rows = await self._fetch(_POLICY_VERSIONS)

        models_by_actor: dict[str, set[str]] = {}
        for row in model_rows:
            models_by_actor.setdefault(row["actor"], set()).add(row["model"])

        actors = tuple(
            FleetActorRecord(
                actor=row["actor"],
                actions=tuple(sorted(row["actions"])),
                succeeded=row["succeeded"],
                denied=row["denied"],
                failed=row["failed"],
                models=tuple(sorted(models_by_actor.get(row["actor"], ()))),
                last_seen_at=row["last_seen_at"],
            )
            for row in actor_rows
        )
        return FleetSnapshotRecord(
            actors=actors,
            denials=tuple(AuditEventRecord(**dict(row)) for row in denial_rows),
            policy_versions=tuple(row["policy_version"] for row in version_rows),
        )

    # -- transport ---------------------------------------------------------

    async def _fetch(self, query: str, *args: Any) -> list[Any]:
        try:
            return await self._pool.fetch(query, *args)
        except Exception as exc:
            raise StateUnavailableError(f"dashboard read failed: {type(exc).__name__}") from exc

    async def _fetchrow(self, query: str, *args: Any) -> Any:
        try:
            return await self._pool.fetchrow(query, *args)
        except Exception as exc:
            raise StateUnavailableError(f"dashboard read failed: {type(exc).__name__}") from exc
