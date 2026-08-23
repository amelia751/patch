"""Starting the work a run describes, without doing it in the request.

A remediation clones a repository, reasons over it several times, builds it,
tests it, has a second agent grade the result, and opens a pull request. That is
minutes, sometimes many. Three places it must therefore not happen:

*Not in the HTTP request.* Cloud Run may reclaim an instance as soon as a
response is written, so a background task started during a request can be killed
after the console has already been told the run began.

*Not in a Pub/Sub push handler.* A push subscription's ack deadline caps at ten
minutes and cannot be raised. Past it Pub/Sub does not fail the delivery — it
redelivers, so a twelve-minute remediation becomes two remediations racing to
open the same pull request.

*Not on a shared web instance at all.* `patchapi-agents` serves change
intelligence at concurrency one; a remediation parked there stalls the lane that
fills the inbox.

So the API writes the run row and starts a job, which is a unit of work Cloud Run
will let run for hours and which outlives whatever asked for it. Locally there is
no Cloud Run, and a subprocess is the honest equivalent: same entry point, same
arguments, same durability guarantee relative to the thing that spawned it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

import httpx

from packages.state.provider_check import (
    REQUEST_TIMEOUT_SECONDS,
    RUN_API,
    SCOPE,
    execution_id,
    gcp_project,
    gcp_region,
    job_path,
)

log = logging.getLogger(__name__)

JOB_VAR: Final[str] = "PATCHAPI_REMEDIATION_JOB"
LOCAL_VAR: Final[str] = "PATCHAPI_REMEDIATION_LOCAL"

ENTRY_POINT: Final[str] = "patchapi-remediate"


class RemediationUnavailableError(RuntimeError):
    """Nothing could be asked to run this remediation."""


@runtime_checkable
class RemediationDispatcher(Protocol):
    """Starts one remediation and returns a handle to whatever is running it."""

    async def dispatch(self, run_id: str) -> str: ...

    @property
    def transport(self) -> str: ...


@dataclass(frozen=True, slots=True)
class CloudRunRemediationDispatcher:
    """Runs the remediation job, once per run id.

    Holds no credentials: the token comes from the API's runtime service account,
    which is granted `run.jobs.run` on this one job and nothing else.

    Unlike the provider poll, a running execution is not a reason to skip. Two
    remediations are two different pieces of work; what stops a change being
    patched twice is the unique run row, decided before this is ever called.
    """

    project: str
    region: str
    job: str

    @property
    def transport(self) -> str:
        return f"cloud-run-job:{self.job}"

    @property
    def resource(self) -> str:
        return job_path(self.project, self.region, self.job)

    async def dispatch(self, run_id: str) -> str:
        token = await _token(self.job)
        # The job image has no run id baked in; the override is what makes one
        # deployed job able to serve every run.
        body: dict[str, Any] = {
            "overrides": {
                "containerOverrides": [{"args": ["--run-id", run_id]}],
                "taskCount": 1,
            }
        }
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
            try:
                response = await client.post(f"{RUN_API}/{self.resource}:run", json=body)
            except (httpx.HTTPError, OSError) as exc:
                raise RemediationUnavailableError(f"Cloud Run did not answer: {exc}") from exc
            if response.status_code >= 400:
                raise RemediationUnavailableError(
                    f"Cloud Run returned {response.status_code} starting {self.job}"
                )
            payload = response.json() if response.content else {}

        name = str(payload.get("name") or "")
        nested = payload.get("response")
        if isinstance(nested, dict) and nested.get("name"):
            name = str(nested["name"])
        started = execution_id(name)
        log.info("dispatched run %s to %s (%s)", run_id, self.job, started or "unnamed")
        return started


@dataclass(frozen=True, slots=True)
class LocalProcessDispatcher:
    """Runs the remediation in a detached child process.

    For a local checkout, where there is no Cloud Run job to trigger. The child
    is detached deliberately: a remediation must not die because the dev server
    reloaded, which is the same property the Cloud Run job has relative to the
    request that started it.
    """

    repo_root: Path
    log_dir: Path

    @property
    def transport(self) -> str:
        return "local-process"

    async def dispatch(self, run_id: str) -> str:
        command = _local_command()
        if command is None:
            raise RemediationUnavailableError(
                f"neither {ENTRY_POINT} nor uv is on PATH; cannot run a remediation locally"
            )
        self.log_dir.mkdir(parents=True, exist_ok=True)
        output = self.log_dir / f"run-{run_id}.log"

        def spawn() -> int:
            with output.open("ab") as sink:
                process = subprocess.Popen(
                    [*command, "--run-id", run_id],
                    cwd=self.repo_root,
                    stdout=sink,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            return process.pid

        pid = await asyncio.to_thread(spawn)
        log.info("dispatched run %s to local pid %d (%s)", run_id, pid, output)
        return f"pid-{pid}"


def _local_command() -> list[str] | None:
    installed = shutil.which(ENTRY_POINT)
    if installed:
        return [installed]
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", ENTRY_POINT]
    return [sys.executable, "-m", "patchapi_remediation.entrypoint"]


async def _token(job: str) -> str:
    def mint() -> str:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(scopes=[SCOPE])
        credentials.refresh(google.auth.transport.requests.Request())
        return str(credentials.token or "")

    try:
        return await asyncio.to_thread(mint)
    except Exception as exc:
        raise RemediationUnavailableError(f"no credentials to run {job}: {exc}") from exc


def build_dispatcher(
    env: dict[str, str] | None = None, *, repo_root: Path | None = None
) -> RemediationDispatcher | None:
    """The dispatcher for this deployment, or None when nothing can run a job.

    None is a legitimate answer and is reported as such. A console that accepted
    "Start remediation" and dropped it would claim a run nobody is performing,
    which is worse than a button that says the lane is not wired.
    """
    environ = os.environ if env is None else env
    job = environ.get(JOB_VAR, "").strip()
    project = gcp_project(env)
    if job and project:
        return CloudRunRemediationDispatcher(project=project, region=gcp_region(env), job=job)

    if environ.get(LOCAL_VAR, "").strip().lower() in {"1", "true", "yes"}:
        root = repo_root or Path(__file__).resolve().parents[2]
        return LocalProcessDispatcher(repo_root=root, log_dir=root / ".runs")
    return None


__all__ = [
    "ENTRY_POINT",
    "JOB_VAR",
    "LOCAL_VAR",
    "CloudRunRemediationDispatcher",
    "LocalProcessDispatcher",
    "RemediationDispatcher",
    "RemediationUnavailableError",
    "build_dispatcher",
]
