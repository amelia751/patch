"""`patchapi-remediate --run-id <uuid>` — one named run, in its own container.

No longer the lane the console uses. `worker.py` performs runs on a warm Cloud
Run worker pool, because this one waited 136s for Cloud Run to find capacity —
measured on the task API, against 5.6s of container — and paid it again when an
operator hold ended the execution and Continue started a second one.

What survives is the reason a remediation is not served on a request, and it is
still right: a Pub/Sub push subscription stops waiting after ten minutes and
redelivers, turning one slow migration into two racing to open the same pull
request, and a background task on a web instance dies whenever Cloud Run
reclaims it. A warm pool is neither of those — it pulls, and its instances are
not reclaimed between runs.

So this stays deployed for the one thing a pool is worse at: performing exactly
the run you name, now, in an isolated container whose logs belong to it alone.
That is what an operator wants when asking why a particular run stopped. The run
id is an argument rather than an environment variable so one deployed job serves
every run, and so a failed run can be replayed with the same command.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from typing import Final

EXIT_MISCONFIGURED: Final[int] = 3


def _logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
    # httpx logs full request URLs at INFO, and a Google API key travels as a
    # query parameter on some surfaces.
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _main(run_id: str) -> int:
    from patchapi_agent_runner.config import ensure_fleet_importable

    ensure_fleet_importable()

    from packages.state.config import database_url
    from packages.state.pool import create_pool
    from patchapi_agent_runner import telemetry
    from patchapi_agent_runner.remediation import job

    provider = telemetry.install(telemetry.SERVICE_REMEDIATE)
    pool = await create_pool(database_url())
    try:
        return await job.execute(pool, run_id)
    except Exception as exc:
        # The pool is still open here, which is the only reason this is caught
        # inside `_main` rather than in `main`: the run has to be told it is over
        # before the connection goes.
        logging.getLogger(__name__).exception("remediation job crashed: %s", exc)
        await job.abandon(pool, run_id, exc)
        return EXIT_MISCONFIGURED
    finally:
        await pool.close()
        # This container exits as soon as the run ends, so an unflushed batch is
        # a lost trace of exactly the run an operator came here to read.
        telemetry.flush(provider)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="the remediation_runs row to execute")
    args = parser.parse_args(argv)

    _logging()
    try:
        return asyncio.run(_main(args.run_id.strip()))
    except KeyboardInterrupt:  # pragma: no cover
        return EXIT_MISCONFIGURED
    except Exception as exc:
        # The run row already carries whatever state was reached. A traceback on
        # stderr is for the operator; the exit code is for Cloud Run.
        logging.getLogger(__name__).exception("remediation job failed: %s", exc)
        return EXIT_MISCONFIGURED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
