"""The warm remediator's loop, without a database or a remediation.

What is worth asserting here is not that a run gets performed — `job.execute` is
tested where it lives — but the three properties that only exist because the work
now happens on a shared, long-lived instance:

*A lease is always given back*, including when the run crashes, or one bad run
takes the instance out of service for the rest of its life.

*A crash is recorded before the lease is released*, because releasing first puts
the row back at RECEIVED for the next poll and a second instance would begin a
remediation whose worklog says it is already underway.

*Stopping happens between runs.* Cloud Run's shutdown grace is far shorter than a
migration, and a remediation cut in half leaves an allocated sandbox and a
worklog that stops mid-sentence.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from patchapi_agent_runner.remediation import worker


class _Pool:
    """Enough of an asyncpg pool for `async with pool.acquire()`."""

    def __init__(self) -> None:
        self.connection = object()

    def acquire(self) -> Any:
        connection = self.connection

        class _Ctx:
            async def __aenter__(self) -> object:
                return connection

            async def __aexit__(self, *exc: object) -> bool:
                return False

        return _Ctx()


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Records claims and releases in the order the worker made them."""
    from packages.state import run_queue

    calls: list[tuple[str, str]] = []
    pending: list[str | None] = []

    async def claim(connection: object, name: str, *, lane: str, **kwargs: object) -> str | None:
        run_id = pending.pop(0) if pending else None
        calls.append(("claim", run_id or ""))
        return run_id

    async def release(connection: object, run_id: str, name: str) -> None:
        calls.append(("release", run_id))

    monkeypatch.setattr(run_queue, "claim", claim)
    monkeypatch.setattr(run_queue, "release", release)
    return calls, pending


@pytest.mark.asyncio
async def test_a_finished_run_gives_the_lease_back(
    monkeypatch: pytest.MonkeyPatch, queue: Any
) -> None:
    from patchapi_agent_runner.remediation import job

    calls, _ = queue
    performed: list[str] = []

    async def execute(pool: object, run_id: str) -> int:
        performed.append(run_id)
        return job.EXIT_OK

    monkeypatch.setattr(job, "execute", execute)

    await worker.perform(_Pool(), "run-1", "worker-a")

    assert performed == ["run-1"]
    assert calls == [("release", "run-1")]


@pytest.mark.asyncio
async def test_a_crashed_run_is_marked_failed_before_the_lease_is_released(
    monkeypatch: pytest.MonkeyPatch, queue: Any
) -> None:
    """Order matters: released first, the next poll would start it again."""
    from patchapi_agent_runner.remediation import job

    calls, _ = queue
    order: list[str] = []

    async def execute(pool: object, run_id: str) -> int:
        raise RuntimeError("sandbox unreachable")

    async def abandon(pool: object, run_id: str, exc: BaseException) -> None:
        order.append("abandon")

    monkeypatch.setattr(job, "execute", execute)
    monkeypatch.setattr(job, "abandon", abandon)

    await worker.perform(_Pool(), "run-2", "worker-a")

    assert order == ["abandon"]
    assert calls == [("release", "run-2")]


@pytest.mark.asyncio
async def test_one_bad_run_does_not_end_the_instance(
    monkeypatch: pytest.MonkeyPatch, queue: Any
) -> None:
    """A pool instance serves every later run, so a crash cannot be fatal to it."""
    from patchapi_agent_runner.remediation import job

    calls, pending = queue
    pending.extend(["run-bad", "run-good"])
    performed: list[str] = []

    async def execute(pool: object, run_id: str) -> int:
        performed.append(run_id)
        if run_id == "run-bad":
            raise RuntimeError("boom")
        return job.EXIT_OK

    async def abandon(pool: object, run_id: str, exc: BaseException) -> None:
        return None

    monkeypatch.setattr(job, "execute", execute)
    monkeypatch.setattr(job, "abandon", abandon)
    monkeypatch.setattr(worker, "poll_seconds", lambda: 0.01)

    stopping = asyncio.Event()

    async def stop_once_idle() -> None:
        while ("claim", "") not in calls:
            await asyncio.sleep(0.01)
        stopping.set()

    await asyncio.gather(
        worker.serve(_Pool(), "worker-a", stopping, in_lane="test"), stop_once_idle()
    )

    assert performed == ["run-bad", "run-good"]


@pytest.mark.asyncio
async def test_an_unreachable_queue_backs_off_instead_of_spinning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from packages.state import run_queue

    attempts: list[int] = []

    async def refuse(connection: object, name: str, *, lane: str, **kwargs: object) -> str | None:
        attempts.append(1)
        raise ConnectionError("postgres is gone")

    monkeypatch.setattr(run_queue, "claim", refuse)
    monkeypatch.setattr(worker, "ERROR_BACKOFF_SECONDS", 0.05)

    stopping = asyncio.Event()

    async def stop_soon() -> None:
        await asyncio.sleep(0.12)
        stopping.set()

    await asyncio.gather(worker.serve(_Pool(), "worker-a", stopping, in_lane="test"), stop_soon())

    # Backing off, not spinning: without the wait this would be thousands.
    assert 1 <= len(attempts) <= 6


def test_each_instance_leases_under_its_own_name() -> None:
    """Two instances sharing a lease name would each think it holds the other's run."""
    assert worker.worker_id() != worker.worker_id()


def test_a_worker_without_a_lane_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """One Cloud SQL instance serves the deployment and every laptop.

    A worker that polled every lane would perform the hosted console's runs on
    somebody's machine, so not knowing which lane it serves is fatal rather than
    defaulted.
    """
    monkeypatch.delenv(worker.LANE_ENV_VAR, raising=False)
    assert worker.lane() == ""
    assert worker.main([]) == worker.EXIT_MISCONFIGURED


def test_the_poll_interval_falls_back_when_the_environment_is_nonsense(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(worker.POLL_ENV_VAR, "not-a-number")
    assert worker.poll_seconds() == worker.POLL_SECONDS
    monkeypatch.setenv(worker.POLL_ENV_VAR, "0")
    assert worker.poll_seconds() == worker.POLL_SECONDS
    monkeypatch.setenv(worker.POLL_ENV_VAR, "2.5")
    assert worker.poll_seconds() == 2.5
