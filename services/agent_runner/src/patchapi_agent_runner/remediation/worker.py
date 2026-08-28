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
from collections.abc import Sequence
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

POLL_ENV_VAR: Final[str] = "PATCHAPI_WORKER_POLL_SECONDS"


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


async def serve(pool: asyncpg.Pool, worker: str, stopping: asyncio.Event) -> None:
    """Claim and perform runs until asked to stop.

    The stop is checked between runs and never inside one. A remediation
    interrupted halfway leaves a sandbox allocated and a half-written worklog, and
    Cloud Run's shutdown grace is far shorter than a migration; letting the
    current run finish is the only ending that keeps the record true.
    """
    from packages.state import run_queue

    delay = poll_seconds()
    while not stopping.is_set():
        try:
            async with pool.acquire() as connection:
                run_id = await run_queue.claim(connection, worker)
        except Exception as exc:
            log.warning("worker %s could not reach the run queue: %s", worker, exc)
            await _wait(stopping, ERROR_BACKOFF_SECONDS)
            continue

        if run_id is None:
            await _wait(stopping, delay)
            continue

        await perform(pool, run_id, worker)


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

    worker = worker_id()
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stopping.set)

    pool = await create_pool(database_url())
    log.info("worker %s ready; polling every %.1fs", worker, poll_seconds())
    try:
        await serve(pool, worker, stopping)
        return EXIT_OK
    finally:
        await pool.close()


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
