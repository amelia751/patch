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
    """Enough of an asyncpg pool for `async with pool.acquire(timeout=...)`."""

    def __init__(self) -> None:
        self.connection = object()
        self.timeouts: list[float | None] = []

    def acquire(self, *, timeout: float | None = None) -> Any:
        connection = self.connection
        self.timeouts.append(timeout)

        class _Ctx:
            async def __aenter__(self) -> object:
                return connection

            async def __aexit__(self, *exc: object) -> bool:
                return False

        return _Ctx()


class _DeadPool:
    """A pool whose every connection is gone, which is how the incident began.

    Cloud SQL dropped the worker's idle sockets and asyncpg kept them, so
    `acquire()` waited for one to come free and none ever did. This is that pool:
    it honours the timeout it is given and refuses, which is the only reason the
    loop gets a chance to log, back off and try again.
    """

    def __init__(self) -> None:
        self.attempts = 0

    def acquire(self, *, timeout: float | None = None) -> Any:
        self.attempts += 1

        class _Ctx:
            async def __aenter__(self) -> object:
                raise TimeoutError("no connection became free")

            async def __aexit__(self, *exc: object) -> bool:
                return False

        return _Ctx()


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Records claims, releases and heartbeats in the order the worker made them."""
    from packages.state import run_queue, worker_registry

    calls: list[tuple[str, str]] = []
    pending: list[str | None] = []

    async def claim(connection: object, name: str, *, lane: str, **kwargs: object) -> str | None:
        run_id = pending.pop(0) if pending else None
        calls.append(("claim", run_id or ""))
        return run_id

    async def release(connection: object, run_id: str, name: str) -> None:
        calls.append(("release", run_id))

    async def beat(
        connection: object, name: str, *, lane: str, run_id: str | None = None
    ) -> None:
        calls.append(("beat", run_id or ""))

    async def forget(connection: object, name: str) -> None:
        calls.append(("forget", name))

    monkeypatch.setattr(run_queue, "claim", claim)
    monkeypatch.setattr(run_queue, "release", release)
    monkeypatch.setattr(worker_registry, "beat", beat)
    monkeypatch.setattr(worker_registry, "forget", forget)
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
    monkeypatch: pytest.MonkeyPatch, queue: Any
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


@pytest.mark.asyncio
async def test_a_pool_with_no_live_connection_keeps_polling(
    monkeypatch: pytest.MonkeyPatch, queue: Any
) -> None:
    """The incident, as a test.

    Every pooled connection had been dropped by Cloud SQL for idleness. With an
    unbounded `acquire()` this loop stopped inside it — no exception, no log, no
    claim — and stayed there for four hours while two runs waited. It has to come
    back round instead, so that a pool which recovers is picked straight back up.
    """
    monkeypatch.setattr(worker, "ERROR_BACKOFF_SECONDS", 0.02)
    dead = _DeadPool()
    stopping = asyncio.Event()

    async def stop_soon() -> None:
        await asyncio.sleep(0.1)
        stopping.set()

    await asyncio.gather(worker.serve(dead, "worker-a", stopping, in_lane="test"), stop_soon())

    assert dead.attempts > 1


@pytest.mark.asyncio
async def test_a_poll_that_hangs_is_given_up_on(
    monkeypatch: pytest.MonkeyPatch, queue: Any
) -> None:
    """The incident's real shape, and why `command_timeout` was not enough.

    The worker's sockets to Cloud SQL were gone without an RST, so each poll
    blocked in the kernel until TCP gave up — fifteen minutes, four hours of them,
    below the level at which asyncpg can cancel anything, because cancelling means
    sending on the same dead connection. The ceiling therefore has to sit outside
    the attempt.
    """
    from packages.state import run_queue

    attempts: list[int] = []

    async def never_answers(
        connection: object, name: str, *, lane: str, **kwargs: object
    ) -> str | None:
        attempts.append(1)
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    monkeypatch.setattr(run_queue, "claim", never_answers)
    monkeypatch.setattr(worker, "POLL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(worker, "ERROR_BACKOFF_SECONDS", 0.01)

    stopping = asyncio.Event()

    async def stop_soon() -> None:
        await asyncio.sleep(0.3)
        stopping.set()

    await asyncio.gather(worker.serve(_Pool(), "worker-a", stopping, in_lane="test"), stop_soon())

    # Came back round instead of waiting out the hang. Before this, one.
    assert len(attempts) > 1


@pytest.mark.asyncio
async def test_every_poll_is_bounded(monkeypatch: pytest.MonkeyPatch, queue: Any) -> None:
    """A poll that waits without limit is a worker that can stop without saying so."""
    calls, _ = queue
    monkeypatch.setattr(worker, "poll_seconds", lambda: 0.01)
    pool = _Pool()
    stopping = asyncio.Event()

    async def stop_once_idle() -> None:
        while ("claim", "") not in calls:
            await asyncio.sleep(0.01)
        stopping.set()

    await asyncio.gather(worker.serve(pool, "worker-a", stopping, in_lane="test"), stop_once_idle())

    assert pool.timeouts
    assert all(timeout is not None and timeout > 0 for timeout in pool.timeouts)


@pytest.mark.asyncio
async def test_a_busy_worker_keeps_saying_it_is_alive(
    monkeypatch: pytest.MonkeyPatch, queue: Any
) -> None:
    """A remediation does not poll while it runs, and runs outlive one beat.

    So the beat cannot only happen at the run's edges. Without this, the last
    thing a busy worker said was "idle", it aged past the liveness window while
    working, and the console reported a worker mid-migration as absent — the
    wrong half of the distinction the heartbeat exists to draw.
    """
    from patchapi_agent_runner.remediation import job

    calls, pending = queue
    pending.append("run-1")

    async def execute(pool: object, run_id: str) -> int:
        # Several heartbeat intervals, as a real remediation is.
        await asyncio.sleep(0.12)
        return job.EXIT_OK

    monkeypatch.setattr(job, "execute", execute)
    monkeypatch.setattr(worker, "poll_seconds", lambda: 0.01)
    monkeypatch.setattr(worker, "HEARTBEAT_SECONDS", 0.02)

    stopping = asyncio.Event()

    async def stop_once_idle() -> None:
        while ("claim", "") not in calls:
            await asyncio.sleep(0.01)
        stopping.set()

    await asyncio.gather(
        worker.serve(_Pool(), "worker-a", stopping, in_lane="test"), stop_once_idle()
    )

    on_this_run = [call for call in calls if call == ("beat", "run-1")]
    assert len(on_this_run) > 1
    # The first beat lands before the run finishes, not after it.
    assert calls.index(("beat", "run-1")) < calls.index(("release", "run-1"))


@pytest.mark.asyncio
async def test_the_heartbeat_stops_when_the_run_does(
    monkeypatch: pytest.MonkeyPatch, queue: Any
) -> None:
    """A finished run must not go on being reported as this worker's current one."""
    from patchapi_agent_runner.remediation import job

    calls, pending = queue
    pending.append("run-1")

    async def execute(pool: object, run_id: str) -> int:
        return job.EXIT_OK

    monkeypatch.setattr(job, "execute", execute)
    monkeypatch.setattr(worker, "poll_seconds", lambda: 0.01)
    monkeypatch.setattr(worker, "HEARTBEAT_SECONDS", 0.01)

    stopping = asyncio.Event()

    async def stop_once_idle() -> None:
        while ("claim", "") not in calls:
            await asyncio.sleep(0.01)
        stopping.set()

    await asyncio.gather(
        worker.serve(_Pool(), "worker-a", stopping, in_lane="test"), stop_once_idle()
    )
    released = calls.index(("release", "run-1"))

    assert ("beat", "run-1") not in calls[released:]


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
