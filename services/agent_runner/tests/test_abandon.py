"""A remediator that dies has to say the run is over.

The entrypoint used to log the traceback and exit non-zero on the belief that
"the run row already carries whatever state was reached". It does — and when the
crash lands during setup, the state reached is RECEIVED, where the console reads
"waiting for the remediator to claim this run" and waits for good. A real GKE
staging failure (`TLS handshake timeout`) left a run there for ten minutes with
nothing running.
"""

from __future__ import annotations

import pytest
from patchapi_agent_runner.remediation import job


class _Recorded:
    """Stands in for `_stop`, capturing the sentence written to the run."""

    def __init__(self) -> None:
        self.run_id: str | None = None
        self.reason: str | None = None

    async def __call__(self, pool: object, run_id: str, reason: str) -> int:
        self.run_id = run_id
        self.reason = reason
        return job.EXIT_FAILED


@pytest.mark.asyncio
async def test_a_crash_names_the_error_and_says_the_run_did_not_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _Recorded()
    monkeypatch.setattr(job, "_stop", recorded)

    await job.abandon(object(), "run-1", RuntimeError("TLS handshake timeout"))

    assert recorded.run_id == "run-1"
    assert recorded.reason is not None
    assert "RuntimeError" in recorded.reason
    assert "TLS handshake timeout" in recorded.reason
    assert "did not finish" in recorded.reason


@pytest.mark.asyncio
async def test_a_database_that_is_also_gone_does_not_mask_the_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The crash is what the operator needs; this path must not raise over it."""

    async def refuse(pool: object, run_id: str, reason: str) -> int:
        raise ConnectionError("pool is closed")

    monkeypatch.setattr(job, "_stop", refuse)

    await job.abandon(object(), "run-2", RuntimeError("original"))
