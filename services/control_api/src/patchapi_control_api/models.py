"""Request and response bodies for the control-plane HTTP surface.

These derive from `StrictModel`, so an unexpected key in a request body is a
rejection rather than something silently dropped, and a response cannot be
mutated between construction and serialization.
"""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime

from packages.schemas.base import StrictModel
from packages.schemas.fields import (
    GitSha,
    NonEmptyLine,
    ProviderId,
    RepoFullName,
    RunId,
    Sha256Hex,
)
from packages.schemas.run_state import RunState
from patchapi_control_api.ports import (
    AuditEventRecord,
    ChangeRecord,
    FleetActorRecord,
    RepositoryImpactRecord,
    RunDetailRecord,
    RunSummaryRecord,
)


class HealthResponse(StrictModel):
    """Liveness. Answers "is this process serving", never "can it do work"."""

    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ReadinessCheck(StrictModel):
    name: str
    ready: bool
    detail: str | None = None


class ReadinessResponse(StrictModel):
    """Readiness, reported per dependency so an operator sees which one is out."""

    status: Literal["ready", "not_ready"]
    service: str
    version: str
    environment: str
    checks: tuple[ReadinessCheck, ...]


class ProviderCheckRequest(StrictModel):
    """A manual trigger to look for changes published by one provider.

    `since` bounds the window to inspect. It must carry a timezone: the value
    feeds the idempotency key, and a naive timestamp would make the same
    request from two machines look like two different requests.
    """

    provider_id: ProviderId
    requested_by: NonEmptyLine
    since: AwareDatetime | None = None


class ProviderCheckResponse(StrictModel):
    """The outcome of a trigger. `created` is false for an accepted replay."""

    provider_id: ProviderId
    idempotency_key: Sha256Hex
    created: bool
    run_id: RunId | None = None


class ChangeListResponse(StrictModel):
    """Provider changes, newest first."""

    changes: tuple[ChangeRecord, ...]


class RepositoryImpactResponse(StrictModel):
    """Per-repository exposure for one change, or across all known changes.

    Unaffected repositories are included rather than filtered out: "we looked
    and found nothing" is a different, weaker claim than "we did not look", and
    the organization view has to be able to tell them apart.
    """

    change_id: NonEmptyLine | None
    repositories: tuple[RepositoryImpactRecord, ...]


class RunListResponse(StrictModel):
    """Remediation runs, most recently started first."""

    runs: tuple[RunSummaryRecord, ...]


class RunDetailResponse(StrictModel):
    """One run's full evidence bundle, plus what the state machine allows next."""

    detail: RunDetailRecord
    terminal: bool
    allowed_next: tuple[RunState, ...]


class FleetResponse(StrictModel):
    """Observed fleet behaviour and refused actions.

    Named `observed_actors` rather than `registered_agents` on purpose: this is
    aggregated from the audit trail, not read from Agent Registry.
    """

    observed_actors: tuple[FleetActorRecord, ...]
    denials: tuple[AuditEventRecord, ...]
    policy_versions: tuple[str, ...]


class RunStateResponse(StrictModel):
    """Deterministic run state, with the moves the state machine still allows.

    `allowed_next` is derived from the shared transition table rather than
    recomputed here, so the dashboard and the orchestrator cannot disagree
    about what may happen next.
    """

    run_id: RunId
    state: RunState
    repository: RepoFullName
    base_sha: GitSha
    updated_at: datetime
    reason: NonEmptyLine | None = None
    terminal: bool
    allowed_next: tuple[RunState, ...]
