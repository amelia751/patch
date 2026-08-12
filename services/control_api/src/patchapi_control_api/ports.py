"""The dependencies the control plane calls out to, as explicit contracts.

The control plane owns HTTP transport, validation, and idempotency-key
derivation. It does not own the workflow database, the event transport, or any
agent. Those arrive as ports so this service can be exercised end to end before
they exist — and so that when they do not exist, the routes fail closed instead
of inventing a run status or an accepted check.

Nothing here executes repository code, and no port is allowed to: the control
plane is explicitly not an execution surface (roadmap §7.2).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from packages.schemas.base import StrictModel
from packages.schemas.fields import (
    AgentId,
    GitSha,
    Identifier,
    NonEmptyLine,
    ProviderId,
    RepoFullName,
    RepoRelativePath,
    RunId,
    Sha256Hex,
)
from packages.schemas.run_state import RunState


class ProviderCheckCommand(StrictModel):
    """A validated request to look for changes published by one provider.

    `idempotency_key` is derived by this service and travels with the command
    so the dispatcher — and eventually Postgres — deduplicates on a value the
    caller cannot influence beyond the inputs it names.
    """

    provider_id: ProviderId
    since: datetime | None
    requested_by: NonEmptyLine
    idempotency_key: Sha256Hex


class ProviderCheckDispatch(StrictModel):
    """What the dispatcher did with a command.

    `created` is false when the key was already known, which is how a replayed
    trigger stays a no-op rather than starting a second run.
    """

    idempotency_key: Sha256Hex
    created: bool
    run_id: RunId | None = None


@runtime_checkable
class ProviderCheckDispatcher(Protocol):
    """Enqueues provider-check commands onto the durable event transport."""

    async def dispatch(self, command: ProviderCheckCommand) -> ProviderCheckDispatch: ...


class RunRecord(StrictModel):
    """The authoritative row for one remediation run, as read from Postgres."""

    run_id: RunId
    state: RunState
    repository: RepoFullName
    base_sha: GitSha
    updated_at: datetime
    reason: NonEmptyLine | None = None


@runtime_checkable
class RunStateReader(Protocol):
    """Reads deterministic run state. Returns `None` for an unknown run."""

    async def read(self, run_id: str) -> RunRecord | None: ...


class ChangeRecord(StrictModel):
    """One normalized provider change, with how far its fan-out has reached.

    Everything on this record originated outside the enterprise (constraint 4).
    `source_sha256` is `None` when no provider snapshot was captured, and the
    dashboard must show that rather than implying the change was evidenced.
    """

    change_id: NonEmptyLine
    provider: ProviderId
    change_kind: str
    title: NonEmptyLine
    source_urls: tuple[str, ...]
    source_sha256: Sha256Hex | None
    affected_identifiers: tuple[Identifier, ...]
    recommended_replacement: Identifier | None
    effective_at: date | None
    detected_at: datetime
    affected_repositories: int
    open_runs: int
    total_runs: int


class UsageRecord(StrictModel):
    """One inventoried API usage, as the repo indexer observed it.

    `detection_layer` travels with the row so the dashboard can separate a
    deterministic literal match from a model's semantic finding (roadmap §11.3).
    """

    identifier: Identifier
    surface: str | None
    file_path: RepoRelativePath
    line_start: int
    line_end: int | None
    detection_layer: str
    confidence: float
    observed_sha: GitSha


class RepositoryImpactRecord(StrictModel):
    """A repository's exposure to one change, from the API usage inventory.

    `index_is_stale` compares the commit the inventory was built from against
    the repository's default branch head as last observed. A stale index means
    the finding count below is evidence about an older commit, which the
    dashboard has to say out loud rather than present as current.
    """

    repository: RepoFullName
    owner_team: str | None
    criticality: str
    affected: bool
    indexed_sha: GitSha | None
    indexed_at: datetime | None
    usage_count: int
    file_count: int
    identifiers: tuple[Identifier, ...]
    usages: tuple[UsageRecord, ...]
    latest_run_id: RunId | None
    latest_run_state: RunState | None


class RunSummaryRecord(StrictModel):
    """One remediation run, at the level of detail a list needs."""

    run_id: RunId
    state: RunState
    repository: RepoFullName
    change_id: NonEmptyLine
    base_sha: GitSha
    trace_id: str | None
    attempts_used: int
    attempt_budget: int
    started_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    failure_reason: str | None


class TransitionRecord(StrictModel):
    """One entry of the append-only run transition log (roadmap §9)."""

    sequence: int
    from_state: RunState | None
    to_state: RunState
    actor: NonEmptyLine
    reason: str | None
    occurred_at: datetime


class PolicyDecisionRecord(StrictModel):
    """A deterministic policy verdict.

    `auto_merge` is carried explicitly so the dashboard can show it as false
    rather than omitting it. Constraint 3 is a claim the UI should display
    being kept, not one the reader has to take on trust.
    """

    decision: str
    risk: str
    auto_patch: bool
    auto_pr: bool
    auto_merge: bool
    forbidden_globs: tuple[str, ...]
    required_checks: tuple[str, ...]
    reason: NonEmptyLine
    policy_version: str
    evaluated_at: datetime


class PatchAttemptRecord(StrictModel):
    """One patch attempt and the sandbox outcome that graded it.

    A `None` exit code means the attempt never ran in isolation. It is not a
    pass: constraint 5 says an unexecuted patch has no result at all.
    """

    attempt_number: int
    status: str
    patch_agent: NonEmptyLine
    patch_model: NonEmptyLine
    prompt_version: str | None
    sandbox_ref: str | None
    build_exit_code: int | None
    test_exit_code: int | None
    diff_sha256: Sha256Hex | None
    files_changed: int | None
    failure_summary: str | None
    started_at: datetime
    ended_at: datetime | None


class VerificationCheckRecord(StrictModel):
    """One named check inside a verification report."""

    name: NonEmptyLine
    passed: bool


class VerificationRecord(StrictModel):
    """An independent verdict on one patch attempt.

    `verifier_agent` and `patch_agent` are both present so the independence
    required by constraint 6 is visible in the response, not merely enforced by
    a database constraint the dashboard cannot see.
    """

    verdict: str
    verifier_agent: NonEmptyLine
    verifier_model: NonEmptyLine
    patch_agent: NonEmptyLine
    patch_model: NonEmptyLine
    checks: tuple[VerificationCheckRecord, ...]
    evidence_summary: str | None
    evaluated_at: datetime
    attempt_number: int


class ArtifactRecord(StrictModel):
    """Evidence metadata. The bytes live in object storage, never in this API."""

    kind: str
    uri: str
    content_sha256: Sha256Hex
    size_bytes: int
    media_type: str
    attempt_number: int | None
    created_at: datetime


class PullRequestRecord(StrictModel):
    """A pull request PatchAPI opened, and what humans did with it afterwards.

    `merged_by_patchapi` exists to be shown false. A merged PR is evidence that
    a human merged it through normal review, not that PatchAPI did.
    """

    number: int
    url: str
    title: NonEmptyLine
    head_branch: NonEmptyLine
    base_branch: NonEmptyLine
    head_sha: GitSha
    state: str
    merged_by_patchapi: bool
    opened_at: datetime
    observed_at: datetime


class RunDetailRecord(StrictModel):
    """Everything one run produced, assembled for the run-detail page."""

    summary: RunSummaryRecord
    change: ChangeRecord
    transitions: tuple[TransitionRecord, ...]
    policy: PolicyDecisionRecord | None
    attempts: tuple[PatchAttemptRecord, ...]
    verification: VerificationRecord | None
    artifacts: tuple[ArtifactRecord, ...]
    pull_request: PullRequestRecord | None
    usages: tuple[UsageRecord, ...]


class AuditEventRecord(StrictModel):
    """One audited action. Denials matter as much as successes."""

    actor: NonEmptyLine
    action: NonEmptyLine
    target: str | None
    outcome: str
    reason: str | None
    trace_id: str | None
    repository: RepoFullName | None
    run_id: RunId | None
    occurred_at: datetime


class FleetActorRecord(StrictModel):
    """An agent or service observed acting, aggregated from the audit trail.

    This is what the fleet *did*, not what an Agent Registry declares it may
    do. Until registry integration lands (roadmap §12.1) the dashboard must not
    present observed behaviour as a declared capability grant.
    """

    actor: AgentId
    actions: tuple[NonEmptyLine, ...]
    succeeded: int
    denied: int
    failed: int
    models: tuple[NonEmptyLine, ...]
    last_seen_at: datetime


class FleetSnapshotRecord(StrictModel):
    """The governance view: who acted, what was refused, under which rules."""

    actors: tuple[FleetActorRecord, ...]
    denials: tuple[AuditEventRecord, ...]
    policy_versions: tuple[str, ...]


@runtime_checkable
class DashboardReader(Protocol):
    """Read-only projections of authoritative state for the dashboard.

    Every method is a query. Nothing here advances a run, writes a row, or
    reaches a provider — the dashboard observes the workflow and never drives
    it. A reader that cannot reach its store raises; the route turns that into
    a fail-closed 503 rather than an empty page that reads as "nothing found".
    """

    async def list_changes(self, *, limit: int) -> tuple[ChangeRecord, ...]: ...

    async def read_change(self, change_id: str) -> ChangeRecord | None: ...

    async def list_repository_impact(
        self, *, change_id: str | None
    ) -> tuple[RepositoryImpactRecord, ...]: ...

    async def list_runs(
        self, *, change_id: str | None, repository: str | None, limit: int
    ) -> tuple[RunSummaryRecord, ...]: ...

    async def read_run_detail(self, run_id: str) -> RunDetailRecord | None: ...

    async def read_fleet_snapshot(self, *, limit: int) -> FleetSnapshotRecord: ...


@dataclass(frozen=True, slots=True)
class ReadinessProbe:
    """A named liveness-independent check of one downstream dependency.

    `check` returns `None` when the dependency is usable, or a short reason
    when it is not. A probe that raises is reported as not ready; readiness
    never fails open.
    """

    name: str
    check: Callable[[], Awaitable[str | None]]
