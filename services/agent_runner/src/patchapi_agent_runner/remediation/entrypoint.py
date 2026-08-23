"""`patchapi-remediate --run-id <uuid>` — the Cloud Run job's command.

A job rather than a request handler, because a remediation takes minutes and
neither of the alternatives survives that. A Pub/Sub push subscription stops
waiting after ten minutes and redelivers, turning one slow migration into two
racing to open the same pull request; a background task on a web instance dies
whenever Cloud Run reclaims it.

The run id is an argument rather than an environment variable so one deployed
job serves every run, and so a failed execution can be replayed by hand with the
same command the console issued.
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
    from patchapi_agent_runner.remediation import job

    pool = await create_pool(database_url())
    try:
        return await job.execute(pool, run_id)
    finally:
        await pool.close()


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
