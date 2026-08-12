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
from datetime import datetime
from typing import Protocol, runtime_checkable

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


@dataclass(frozen=True, slots=True)
class ReadinessProbe:
    """A named liveness-independent check of one downstream dependency.

    `check` returns `None` when the dependency is usable, or a short reason
    when it is not. A probe that raises is reported as not ready; readiness
    never fails open.
    """

    name: str
    check: Callable[[], Awaitable[str | None]]
