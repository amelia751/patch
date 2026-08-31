"""In-memory stand-ins for the ports the control plane depends on.

These are the fakes that let the state-read and trigger paths be exercised
before Postgres and Pub/Sub are wired. They are test doubles, never importable
from the service package: nothing in `src/` may fall back to them at runtime.
"""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from patchapi_control_api.app import create_app
from patchapi_control_api.ports import (
    ChangeRecord,
    FleetActorRecord,
    FleetSnapshotRecord,
    PolicyDecisionRecord,
    ProviderCheckCommand,
    ProviderCheckDispatch,
    RepositoryImpactRecord,
    RunDetailRecord,
    RunRecord,
    RunSummaryRecord,
    TransitionRecord,
    UsageRecord,
)

from packages.schemas.run_state import RunState

FIXTURE_RUN_ID = "run-000000000001"
FIXTURE_BASE_SHA = "c5428cdcdcd12204e1f4cc47c393dc6e738d88b2"
FIXTURE_CHANGE_ID = "imagen4-retirement-2026-08-17"
FIXTURE_REPOSITORY = "amelia751/storygen"


class RecordingDispatcher:
    """Deduplicates on the idempotency key, the way the real transport must."""

    def __init__(self) -> None:
        self.commands: list[ProviderCheckCommand] = []
        self._runs: dict[str, str] = {}

    async def dispatch(self, command: ProviderCheckCommand) -> ProviderCheckDispatch:
        self.commands.append(command)
        known = self._runs.get(command.idempotency_key)
        if known is not None:
            return ProviderCheckDispatch(
                idempotency_key=command.idempotency_key, created=False, run_id=known
            )
        run_id = f"run-{len(self._runs) + 1:012d}"
        self._runs[command.idempotency_key] = run_id
        return ProviderCheckDispatch(
            idempotency_key=command.idempotency_key, created=True, run_id=run_id
        )


class DictRunStateReader:
    def __init__(self, records: dict[str, RunRecord] | None = None) -> None:
        self.records = records or {}

    async def read(self, run_id: str) -> RunRecord | None:
        return self.records.get(run_id)


FIXTURE_CHANGE = ChangeRecord(
    change_id=FIXTURE_CHANGE_ID,
    provider="google",
    change_kind="MODEL_RETIREMENT",
    title="Imagen 4 model family retirement",
    source_urls=("https://ai.google.dev/gemini-api/docs/deprecations",),
    # None on purpose: the fixture records no captured provider snapshot, and
    # the dashboard has to be able to render that honestly.
    source_sha256=None,
    affected_identifiers=("imagen-4.0-generate-001",),
    recommended_replacement="gemini-3.1-flash-image",
    effective_at=date(2026, 8, 17),
    detected_at=datetime(2026, 8, 11, 23, 41, tzinfo=UTC),
    affected_repositories=1,
    open_runs=0,
    total_runs=1,
)

FIXTURE_USAGE = UsageRecord(
    identifier="imagen-4.0-generate-001",
    surface=None,
    file_path="cli/src/cli/cli.ts",
    line_start=418,
    line_end=None,
    detection_layer="A_DETERMINISTIC",
    confidence=1.0,
    observed_sha=FIXTURE_BASE_SHA,
)

FIXTURE_RUN_SUMMARY = RunSummaryRecord(
    run_id=FIXTURE_RUN_ID,
    state=RunState.VERIFYING,
    repository=FIXTURE_REPOSITORY,
    change_id=FIXTURE_CHANGE_ID,
    base_sha=FIXTURE_BASE_SHA,
    trace_id="trace-0001",
    attempts_used=2,
    attempt_budget=3,
    started_at=datetime(2026, 8, 11, 23, 45, tzinfo=UTC),
    updated_at=datetime(2026, 8, 11, 23, 55, tzinfo=UTC),
    ended_at=None,
    failure_reason=None,
)


class DictDashboardReader:
    """Serves fixed projections. Unknown ids are absent, never empty records."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def list_changes(self, *, limit: int) -> tuple[ChangeRecord, ...]:
        self.calls.append("list_changes")
        return (FIXTURE_CHANGE,)

    async def read_change(self, change_id: str) -> ChangeRecord | None:
        return FIXTURE_CHANGE if change_id == FIXTURE_CHANGE_ID else None

    async def list_repository_impact(
        self, *, change_id: str | None
    ) -> tuple[RepositoryImpactRecord, ...]:
        if change_id is not None and change_id != FIXTURE_CHANGE_ID:
            return ()
        return (
            RepositoryImpactRecord(
                repository=FIXTURE_REPOSITORY,
                owner_team="media-platform",
                criticality="medium",
                affected=True,
                indexed_sha=FIXTURE_BASE_SHA,
                indexed_at=datetime(2026, 8, 11, 23, 41, tzinfo=UTC),
                usage_count=1,
                file_count=1,
                identifiers=("imagen-4.0-generate-001",),
                usages=(FIXTURE_USAGE,),
                latest_run_id=FIXTURE_RUN_ID,
                latest_run_state=RunState.VERIFYING,
            ),
        )

    async def list_runs(
        self, *, change_id: str | None, repository: str | None, limit: int
    ) -> tuple[RunSummaryRecord, ...]:
        return (FIXTURE_RUN_SUMMARY,)

    async def read_run_detail(self, run_id: str) -> RunDetailRecord | None:
        if run_id != FIXTURE_RUN_ID:
            return None
        return RunDetailRecord(
            summary=FIXTURE_RUN_SUMMARY,
            change=FIXTURE_CHANGE,
            transitions=(
                TransitionRecord(
                    sequence=1,
                    from_state=None,
                    to_state=RunState.RECEIVED,
                    actor="orchestrator",
                    reason="provider-change-detected",
                    occurred_at=datetime(2026, 8, 11, 23, 45, tzinfo=UTC),
                ),
            ),
            policy=PolicyDecisionRecord(
                decision="ALLOW",
                risk="medium",
                auto_patch=True,
                auto_pr=True,
                auto_merge=False,
                forbidden_globs=(".github/workflows/**",),
                required_checks=("build",),
                reason="Provider model-family migration changes runtime semantics.",
                policy_version="2026.08.1",
                evaluated_at=datetime(2026, 8, 11, 23, 46, tzinfo=UTC),
            ),
            attempts=(),
            verification=None,
            artifacts=(),
            pull_request=None,
            usages=(FIXTURE_USAGE,),
        )

    async def read_fleet_snapshot(self, *, limit: int) -> FleetSnapshotRecord:
        return FleetSnapshotRecord(
            actors=(
                FleetActorRecord(
                    actor="patch_agent",
                    actions=("patch.write_path",),
                    succeeded=0,
                    denied=1,
                    failed=0,
                    models=("gemini-3.5-flash",),
                    last_seen_at=datetime(2026, 8, 11, 23, 52, tzinfo=UTC),
                ),
            ),
            denials=(),
            policy_versions=("2026.08.1",),
        )


@pytest.fixture
def dashboard_reader() -> DictDashboardReader:
    return DictDashboardReader()


@pytest.fixture
def run_record() -> RunRecord:
    return RunRecord(
        run_id=FIXTURE_RUN_ID,
        state=RunState.VERIFYING,
        repository="amelia751/storygen",
        base_sha=FIXTURE_BASE_SHA,
        updated_at=datetime(2026, 8, 11, 23, 0, tzinfo=UTC),
    )


@pytest.fixture
def dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest.fixture
def unwired_client() -> TestClient:
    """A client for an app with no ports supplied — the fail-closed baseline."""
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def client(
    dispatcher: RecordingDispatcher,
    run_record: RunRecord,
    dashboard_reader: DictDashboardReader,
) -> TestClient:
    app = create_app(
        provider_check_dispatcher=dispatcher,
        run_state_reader=DictRunStateReader({run_record.run_id: run_record}),
        dashboard_reader=dashboard_reader,
    )
    return TestClient(app, raise_server_exceptions=False)
