"""In-memory stand-ins for the ports the control plane depends on.

These are the fakes that let the state-read and trigger paths be exercised
before Postgres and Pub/Sub are wired. They are test doubles, never importable
from the service package: nothing in `src/` may fall back to them at runtime.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from patchapi_control_api.app import create_app
from patchapi_control_api.ports import (
    ProviderCheckCommand,
    ProviderCheckDispatch,
    RunRecord,
)

from packages.schemas.run_state import RunState

FIXTURE_RUN_ID = "run-000000000001"
FIXTURE_BASE_SHA = "c09e1a44200ff5e951746e013035e68aeb3a14b1"


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


@pytest.fixture
def run_record() -> RunRecord:
    return RunRecord(
        run_id=FIXTURE_RUN_ID,
        state=RunState.VERIFYING,
        repository="amelia751/egaki",
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
def client(dispatcher: RecordingDispatcher, run_record: RunRecord) -> TestClient:
    app = create_app(
        provider_check_dispatcher=dispatcher,
        run_state_reader=DictRunStateReader({run_record.run_id: run_record}),
    )
    return TestClient(app, raise_server_exceptions=False)
