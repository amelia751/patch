"""`patchapi-remediation-worker` — the always-on remediator.

The same remediation as `patchapi-remediate`, performed by a warm instance that
was already running when the operator pressed the button rather than by a
container started to answer it.

Why this exists. `entrypoint.py` is one Cloud Run job execution per run, and the
job docstring argued for that over a request handler because a remediation takes
minutes. That argument is still right about requests and wrong about the
conclusion. Measured on the Cloud Run task API — not the execution API, which
reports a misleading `+13s` — a task that did nothing but read one row waited
136.0s for an instance and then lived 5.6s. The wait is Cloud Run finding
capacity, not our 148 MB image and not our 190ms of imports, and there is no
`min-instances` on a job to keep one ready. Worse, an operator hold ends the
execution, so Continue paid the 136s a second time.

A Cloud Run worker pool is the primitive for this: pull-based, no HTTP surface,
minimum instances, and it stays alive across the hold so the resume costs a poll
interval instead of a second cold provision.

What this does *not* change. The work is `job.execute`, unedited — the same state
machine, the same sandbox boundary, the same independent verification, the same
stop at the pull request. This module only decides which run to perform and when
to stop, so that nothing about the remediation depends on how its process was
started.

One run at a time per instance. A remediation holds a sandbox and drives a state
machine keyed on a single run row; concurrency belongs in the number of
instances, where the pool can account for it, not in a task group here.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import socket
import sys
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

log = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_MISCONFIGURED: Final[int] = 3

# How long an idle instance waits before asking again. This is the latency an
# operator sees between pressing the button and the run being claimed, so it is
# short; the query it repeats is one indexed lookup that returns no rows.
POLL_SECONDS: Final[float] = 1.0

# After a failed poll. The database being briefly unreachable should not become a
# tight loop against it, and an instance that backs off here still has its lease
# on nothing, so no run is held up by the wait.
ERROR_BACKOFF_SECONDS: Final[float] = 5.0

# The hard ceiling on one poll, covering both getting a connection and using it.
#
# Not redundant with the pool's `command_timeout`, which is what the evidence
# says. A worker's connections to Cloud SQL were silently dead — the sockets were
# gone without an RST, so writes went into the void — and this loop retried every
# fifteen minutes rather than every five seconds. Fifteen minutes is the operating
# system's TCP retransmit ceiling: each poll blocked in the kernel, below the
# level asyncpg's own timeout can reach, because cancelling a statement means
# sending on a connection that is equally gone.
#
# So the timeout has to be outside the whole attempt. A poll cannot be worth more
# than a few seconds — it is one indexed lookup — and one that takes longer has
# already failed whether or not anything told us.
POLL_TIMEOUT_SECONDS: Final[float] = 15.0

# How often a worker mid-remediation says it is still there. The poll loop's own
# heartbeat stops for the length of a run, which is minutes, so this is what
# stands in for it. Comfortably inside `worker_registry.ALIVE_SECONDS`, which
# leaves room for a couple of these to fail without the worker being called dead.
HEARTBEAT_SECONDS: Final[float] = 20.0

POLL_ENV_VAR: Final[str] = "PATCHAPI_WORKER_POLL_SECONDS"
# Deliberately the same variable the control plane reads to decide it has a warm
# pool. Two names for one lane is how the API writes runs into a lane nothing
# polls, and the console then shows a run that never starts.
LANE_ENV_VAR: Final[str] = "PATCHAPI_REMEDIATION_WORKER_POOL"


def lane() -> str:
    """Which runs this worker is allowed to claim.

    The same value the control plane has in `PATCHAPI_REMEDIATION_WORKER_POOL`,
    which is what it writes onto a run row when it dispatches. One Cloud SQL
    instance serves the deployment and every laptop with the proxy open, so a
    worker without a lane claims other environments' runs — a hosted run gets
    performed on somebody's machine, against a sandbox and a console nobody is
    watching, and the operator sees a run that stopped for no reason.

    No default. Guessing `local` here would make a misconfigured Cloud Run pool
    silently start serving developers' runs, which is the failure this prevents.
    """
    return os.environ.get(LANE_ENV_VAR, "").strip()


def worker_id() -> str:
    """A name for this instance, stable for its lifetime and unique across the pool.

    Written into the lease, so it is what says which instance is performing a run
    when two are running. Cloud Run sets no per-instance identifier a container
    can read, hence the hostname plus a short random suffix: the hostname alone
    repeats across instances often enough to make one lease look like another's.
    """
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


def poll_seconds() -> float:
    """Seconds between polls of an idle instance."""
    raw = os.environ.get(POLL_ENV_VAR, "").strip()
    try:
        value = float(raw)
    except ValueError:
        return POLL_SECONDS
    return value if value > 0 else POLL_SECONDS


async def perform(pool: asyncpg.Pool, run_id: str, worker: str) -> None:
    """Perform one claimed run and give up the lease however it ends.

    A crash is recorded on the run before the lease is released. Releasing first
    would put a row a nobody is performing back at `RECEIVED` for the next poll to
    claim, and the next instance would begin a remediation whose evidence says it
    is already underway.
    """
    from packages.state import run_queue
    from patchapi_agent_runner.remediation import job

    log.info("worker %s performing run %s", worker, run_id)
    try:
        code = await job.execute(pool, run_id)
        log.info("run %s finished with %s", run_id, code)
    except Exception as exc:
        log.exception("run %s crashed: %s", run_id, exc)
        await job.abandon(pool, run_id, exc)
    finally:
        async with pool.acquire() as connection:
            await run_queue.release(connection, run_id, worker)


async def serve(pool: asyncpg.Pool, worker: str, stopping: asyncio.Event, *, in_lane: str) -> None:
    """Claim and perform runs in one lane until asked to stop.

    The stop is checked between runs and never inside one. A remediation
    interrupted halfway leaves a sandbox allocated and a half-written worklog, and
    Cloud Run's shutdown grace is far shorter than a migration; letting the
    current run finish is the only ending that keeps the record true.

    Every poll is bounded and writes a heartbeat. Both exist because of the same
    incident: the worker's connections to Cloud SQL died silently, each poll
    blocked in the kernel for the TCP retransmit ceiling, and this loop went four
    hours between attempts while runs it should have claimed waited. A bounded
    poll turns that into the error the `except` below already knew how to
    survive, and the heartbeat is what lets anything outside this process tell a
    busy worker from an absent one.
    """
    delay = poll_seconds()
    while not stopping.is_set():
        try:
            run_id = await asyncio.wait_for(
                _poll(pool, worker, in_lane), timeout=POLL_TIMEOUT_SECONDS
            )
        except Exception as exc:
            log.warning("worker %s could not reach the run queue: %s", worker, exc)
            await _wait(stopping, ERROR_BACKOFF_SECONDS)
            continue

        if run_id is None:
            await _wait(stopping, delay)
            continue

        async with _beating(pool, worker, in_lane, run_id):
            await perform(pool, run_id, worker)


async def _poll(pool: asyncpg.Pool, worker: str, in_lane: str) -> str | None:
    """One heartbeat and one claim, on one connection. Returns a run or None."""
    from packages.state import run_queue, worker_registry
    from packages.state.pool import acquire

    async with acquire(pool) as connection:
        await worker_registry.beat(connection, worker, lane=in_lane)
        return await run_queue.claim(connection, worker, lane=in_lane)


@contextlib.asynccontextmanager
async def _beating(
    pool: asyncpg.Pool, worker: str, in_lane: str, run_id: str
) -> AsyncIterator[None]:
    """Keep saying this worker is alive and on `run_id` for as long as it is.

    A remediation does not poll while it runs, so the loop's own heartbeat stops
    for the duration. Without this the last thing a busy worker said was "idle",
    and a run of ordinary length outlived the liveness window — so a worker
    patiently working would be reported to the operator as absent, which is
    exactly the wrong half of the distinction this was added to draw.
    """
    beat = asyncio.create_task(_beat_until_cancelled(pool, worker, in_lane, run_id))
    try:
        yield
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat


async def _beat_until_cancelled(
    pool: asyncpg.Pool, worker: str, in_lane: str, run_id: str
) -> None:
    while True:
        await _announce(pool, worker, in_lane, run_id)
        await asyncio.sleep(HEARTBEAT_SECONDS)


async def _announce(pool: asyncpg.Pool, worker: str, in_lane: str, run_id: str) -> None:
    """Record that this worker is alive and spending its time on `run_id`."""
    from packages.state import worker_registry
    from packages.state.pool import acquire

    try:
        async with acquire(pool) as connection:
            await worker_registry.beat(connection, worker, lane=in_lane, run_id=run_id)
    except Exception as exc:
        # Diagnostic only. The run is already claimed and must go ahead.
        log.warning("worker %s could not record that it started %s: %s", worker, run_id, exc)


async def _wait(stopping: asyncio.Event, seconds: float) -> None:
    """Sleep, but wake immediately if the pool is being shut down."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stopping.wait(), timeout=seconds)


def _logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
    # httpx logs full request URLs at INFO, and a Google API key travels as a
    # query parameter on some surfaces.
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _main() -> int:
    from patchapi_agent_runner.config import ensure_fleet_importable

    ensure_fleet_importable()

    from packages.state.config import database_url
    from packages.state.pool import create_pool
    from patchapi_agent_runner import telemetry

    in_lane = lane()
    if not in_lane:
        # Refusing to start is the point. A worker that polled every lane would
        # perform runs belonging to the deployment, or to another developer.
        log.error("%s is unset; a worker must know which lane it serves", LANE_ENV_VAR)
        return EXIT_MISCONFIGURED

    worker = worker_id()
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stopping.set)

    provider = telemetry.install(telemetry.SERVICE_REMEDIATION_WORKER)
    pool = await create_pool(database_url())
    log.info("worker %s ready in lane %s; polling every %.1fs", worker, in_lane, poll_seconds())
    try:
        await serve(pool, worker, stopping, in_lane=in_lane)
        return EXIT_OK
    finally:
        await _stand_down(pool, worker)
        await pool.close()
        telemetry.flush(provider)


async def _stand_down(pool: asyncpg.Pool, worker: str) -> None:
    """Drop this worker's heartbeat so a deliberate stop does not read as a fault."""
    from packages.state import worker_registry
    from packages.state.pool import acquire

    try:
        async with acquire(pool) as connection:
            await worker_registry.forget(connection, worker)
    except Exception as exc:  # pragma: no cover - shutdown is best effort
        log.warning("worker %s could not clear its heartbeat: %s", worker, exc)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Perform remediation runs as they are requested.")
    parser.parse_args(argv)

    _logging()
    try:
        return asyncio.run(_main())
    except KeyboardInterrupt:  # pragma: no cover
        return EXIT_OK
    except Exception as exc:
        logging.getLogger(__name__).exception("remediation worker failed: %s", exc)
        return EXIT_MISCONFIGURED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
